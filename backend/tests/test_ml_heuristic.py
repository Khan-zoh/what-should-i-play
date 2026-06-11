import math

from app.ml.content import ContentScore
from app.ml.heuristic import EXCLUDED_STATUSES, score_candidates
from app.ml.types import GameFeatures, UserProfile
from app.ml.weights import DEFAULT_WEIGHTS


def _profile(**kw) -> UserProfile:
    return UserProfile(**kw)


def test_content_channel_overrides_genre_jaccard() -> None:
    # Both candidates share zero genres with high_rated_genres, but the content
    # channel says candidate 1 is semantically close.
    profile = _profile(high_rated_genres=frozenset({"RPG"}))
    a = GameFeatures(game_id=1, slug="a", name="A", hours_played=5.0)
    b = GameFeatures(game_id=2, slug="b", name="B", hours_played=5.0)
    content = {
        1: ContentScore(similarity=0.9, nearest_slug="hades", nearest_name="Hades"),
        2: ContentScore(similarity=0.1, nearest_slug="hades", nearest_name="Hades"),
    }
    ranked = score_candidates(profile, [b, a], DEFAULT_WEIGHTS, content=content)
    assert [c.game_id for c in ranked] == [1, 2]
    assert "SIMILAR_TO_HIGH_RATED_GAME:hades" in ranked[0].reason_codes
    # Genre-based code must NOT appear on the embedding path.
    assert not any(
        c.startswith("SIMILAR_TO_HIGH_RATED:") for c in ranked[0].reason_codes
    )


def test_content_channel_code_requires_similarity_threshold() -> None:
    profile = _profile()
    a = GameFeatures(game_id=1, slug="a", name="A", hours_played=5.0)
    content = {1: ContentScore(similarity=0.2, nearest_slug="hades", nearest_name="Hades")}
    [scored] = score_candidates(profile, [a], DEFAULT_WEIGHTS, content=content)
    assert not any(c.startswith("SIMILAR_TO_HIGH_RATED_GAME:") for c in scored.reason_codes)
    # The similarity still contributes to the score even below the code threshold.
    assert scored.contributions["content_similarity"] > 0.0


def test_content_none_keeps_jaccard_path() -> None:
    profile = _profile(high_rated_genres=frozenset({"RPG"}))
    a = GameFeatures(game_id=1, slug="a", name="A", genres=frozenset({"RPG"}), hours_played=5.0)
    [scored] = score_candidates(profile, [a], DEFAULT_WEIGHTS, content=None)
    assert "SIMILAR_TO_HIGH_RATED:RPG" in scored.reason_codes


def test_nan_critic_score_keeps_ranking_deterministic() -> None:
    # A NaN critic_score from external data must not make the sort input-order
    # dependent (NaN comparisons are all False).
    profile = _profile()
    a = GameFeatures(
        game_id=1, slug="a", name="A", critic_score=float("nan"), hours_played=5.0
    )
    b = GameFeatures(game_id=2, slug="b", name="B", hours_played=5.0)
    forward = [c.game_id for c in score_candidates(profile, [a, b], DEFAULT_WEIGHTS)]
    backward = [c.game_id for c in score_candidates(profile, [b, a], DEFAULT_WEIGHTS)]
    assert forward == backward
    assert all(math.isfinite(c.score) for c in score_candidates(profile, [a, b], DEFAULT_WEIGHTS))


def test_contributions_sum_to_score_with_expected_keys() -> None:
    profile = _profile(
        liked_genres=frozenset({"RPG"}), high_rated_genres=frozenset({"RPG"})
    )
    cand = GameFeatures(
        game_id=1, slug="a", name="A", genres=frozenset({"RPG"}),
        critic_score=85.0, hours_played=0.0, status="backlog",
    )
    [sc] = score_candidates(profile, [cand], DEFAULT_WEIGHTS)
    assert abs(sum(sc.contributions.values()) - sc.score) < 1e-9
    assert set(sc.contributions) == {
        "personal_match",
        "content_similarity",
        "quality",
        "backlog_boost",
        "penalties",
    }


def test_liked_genre_outranks_neutral() -> None:
    profile = _profile(liked_genres=frozenset({"RPG"}))
    rpg = GameFeatures(game_id=1, slug="a", name="A", genres=frozenset({"RPG"}))
    neutral = GameFeatures(game_id=2, slug="b", name="B", genres=frozenset({"Sports"}))
    ranked = score_candidates(profile, [neutral, rpg], DEFAULT_WEIGHTS)
    assert [c.game_id for c in ranked] == [1, 2]
    assert "MATCHES_LIKED_GENRE:RPG" in ranked[0].reason_codes


def test_disliked_genre_penalized() -> None:
    profile = _profile(disliked_genres=frozenset({"Horror"}))
    horror = GameFeatures(game_id=1, slug="a", name="A", genres=frozenset({"Horror"}))
    plain = GameFeatures(game_id=2, slug="b", name="B", genres=frozenset({"Puzzle"}))
    ranked = score_candidates(profile, [horror, plain], DEFAULT_WEIGHTS)
    assert ranked[0].game_id == 2


def test_excluded_statuses_are_dropped() -> None:
    profile = _profile()
    keep = GameFeatures(game_id=1, slug="a", name="A")
    for bad in EXCLUDED_STATUSES:
        cand = GameFeatures(game_id=2, slug="b", name="B", status=bad)
        ranked = score_candidates(profile, [keep, cand], DEFAULT_WEIGHTS)
        assert [c.game_id for c in ranked] == [1]


def test_unplayed_and_backlog_reason_codes() -> None:
    profile = _profile()
    cand = GameFeatures(
        game_id=1, slug="a", name="A", hours_played=0.0, status="backlog"
    )
    [scored] = score_candidates(profile, [cand], DEFAULT_WEIGHTS)
    assert "OWNED_AND_UNPLAYED" in scored.reason_codes
    assert "BACKLOG_PRIORITY" in scored.reason_codes


def test_high_critic_and_similar_to_high_rated_codes() -> None:
    profile = _profile(high_rated_genres=frozenset({"RPG"}))
    cand = GameFeatures(
        game_id=1, slug="a", name="A", genres=frozenset({"RPG"}), critic_score=92.0,
        hours_played=5.0,
    )
    [scored] = score_candidates(profile, [cand], DEFAULT_WEIGHTS)
    assert "HIGH_CRITIC_SCORE" in scored.reason_codes
    assert "SIMILAR_TO_HIGH_RATED:RPG" in scored.reason_codes


def test_completed_and_low_rated_sink() -> None:
    profile = _profile()
    completed = GameFeatures(game_id=1, slug="a", name="A", status="completed", hours_played=5.0)
    fresh = GameFeatures(game_id=2, slug="b", name="B", hours_played=0.0)
    ranked = score_candidates(profile, [completed, fresh], DEFAULT_WEIGHTS)
    assert ranked[0].game_id == 2


def test_fallback_reason_code_when_nothing_fires() -> None:
    profile = _profile()
    cand = GameFeatures(game_id=1, slug="a", name="A", hours_played=5.0)
    [scored] = score_candidates(profile, [cand], DEFAULT_WEIGHTS)
    assert scored.reason_codes == ["IN_YOUR_LIBRARY"]


def test_deterministic_tiebreak_by_game_id() -> None:
    profile = _profile()
    a = GameFeatures(game_id=5, slug="a", name="A", hours_played=5.0)
    b = GameFeatures(game_id=2, slug="b", name="B", hours_played=5.0)
    ranked = score_candidates(profile, [a, b], DEFAULT_WEIGHTS)
    assert [c.game_id for c in ranked] == [2, 5]

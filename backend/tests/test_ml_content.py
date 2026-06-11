import numpy as np

from app.ml.content import HighRatedItem, content_scores


def _v(*xs: float) -> np.ndarray:
    return np.array(xs, dtype=np.float32)


def test_similarity_to_centroid_and_nearest_neighbor() -> None:
    # High-rated games cluster near the x axis; candidate 1 is close, candidate 2 far.
    high = [
        HighRatedItem(game_id=10, slug="hades", name="Hades", vector=_v(1.0, 0.0)),
        HighRatedItem(game_id=11, slug="celeste", name="Celeste", vector=_v(0.9, 0.1)),
    ]
    vecs = {1: _v(1.0, 0.05), 2: _v(0.0, 1.0)}
    scores = content_scores(vecs, high)

    assert scores[1].similarity > scores[2].similarity
    assert scores[1].nearest_slug == "hades"
    assert scores[1].nearest_name == "Hades"


def test_negative_cosine_clamped_to_zero() -> None:
    high = [HighRatedItem(game_id=10, slug="a", name="A", vector=_v(1.0, 0.0))]
    scores = content_scores({1: _v(-1.0, 0.0)}, high)
    assert scores[1].similarity == 0.0


def test_leave_one_out_excludes_self() -> None:
    # Candidate 10 IS a high-rated game; its own vector must not inflate its score.
    high = [
        HighRatedItem(game_id=10, slug="hades", name="Hades", vector=_v(1.0, 0.0)),
        HighRatedItem(game_id=11, slug="celeste", name="Celeste", vector=_v(0.0, 1.0)),
    ]
    scores = content_scores({10: _v(1.0, 0.0)}, high)
    # Self excluded: centroid for candidate 10 is just celeste's vector (orthogonal).
    assert scores[10].similarity == 0.0
    assert scores[10].nearest_slug == "celeste"


def test_single_high_rated_candidate_is_itself_no_signal() -> None:
    high = [HighRatedItem(game_id=10, slug="hades", name="Hades", vector=_v(1.0, 0.0))]
    scores = content_scores({10: _v(1.0, 0.0)}, high)
    assert scores[10].similarity == 0.0
    assert scores[10].nearest_slug is None


def test_no_high_rated_returns_empty() -> None:
    assert content_scores({1: _v(1.0, 0.0)}, []) == {}


def test_nearest_tie_broken_by_game_id() -> None:
    high = [
        HighRatedItem(game_id=20, slug="later", name="Later", vector=_v(1.0, 0.0)),
        HighRatedItem(game_id=10, slug="earlier", name="Earlier", vector=_v(1.0, 0.0)),
    ]
    scores = content_scores({1: _v(1.0, 0.0)}, high)
    assert scores[1].nearest_slug == "earlier"  # lower game_id wins the tie

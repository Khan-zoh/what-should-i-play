from app.ml.explanations import explain


def test_unplayed_liked_genre_sentence() -> None:
    s = explain(["OWNED_AND_UNPLAYED", "MATCHES_LIKED_GENRE:RPG"])
    assert s.startswith("Recommended because it")
    assert "unplayed" in s
    assert "RPG" in s
    assert s.endswith(".")


def test_multiple_liked_genres_listed() -> None:
    s = explain(["MATCHES_LIKED_GENRE:RPG", "MATCHES_LIKED_GENRE:Adventure"])
    assert "RPG" in s and "Adventure" in s


def test_high_critic_and_backlog() -> None:
    s = explain(["HIGH_CRITIC_SCORE", "BACKLOG_PRIORITY"])
    assert "review" in s.lower()
    assert "backlog" in s.lower()


def test_similar_to_high_rated_game_humanizes_slug() -> None:
    s = explain(["SIMILAR_TO_HIGH_RATED_GAME:hollow-knight"])
    assert "Hollow Knight" in s
    assert "similar" in s.lower()
    # The generic "resembles" clause must not double-fire for the _GAME code.
    assert "resembles" not in s.lower()


def test_fallback_is_non_empty() -> None:
    s = explain(["IN_YOUR_LIBRARY"])
    assert "library" in s.lower()
    assert s.endswith(".")


def test_empty_codes_still_non_empty() -> None:
    s = explain([])
    assert len(s) > 0
    assert s.endswith(".")

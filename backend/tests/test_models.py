from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    DataSyncRun,
    Game,
    GameEmbedding,
    GameTag,
    LibraryEntry,
    LLMCache,
    Preferences,
    Rating,
    RecommendationEvent,
    UserGameState,
)


def _make_game(session: Session, name: str = "Hollow Knight", slug: str = "hollow-knight") -> Game:
    game = Game(name=name, slug=slug)
    session.add(game)
    session.commit()
    return game


def test_game_can_be_created(db_session: Session) -> None:
    game = _make_game(db_session)
    assert game.id is not None
    assert game.created_at is not None


def test_game_slug_is_unique(db_session: Session) -> None:
    _make_game(db_session)
    with pytest.raises(IntegrityError):
        _make_game(db_session, name="Another", slug="hollow-knight")


def test_library_entry_one_per_game(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(LibraryEntry(game_id=game.id, source="steam", hours_played=12.5))
    db_session.commit()
    db_session.add(LibraryEntry(game_id=game.id, source="manual"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_rating_round_trips(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(Rating(game_id=game.id, enjoyment=5, finished=True, notes="loved it"))
    db_session.commit()
    row = db_session.query(Rating).filter_by(game_id=game.id).one()
    assert row.enjoyment == 5
    assert row.finished is True
    assert row.notes == "loved it"


def test_preferences_singleton_pattern(db_session: Session) -> None:
    db_session.add(
        Preferences(id=1, liked_genres=["rpg", "puzzle"], disliked_genres=["horror"])
    )
    db_session.commit()
    p = db_session.get(Preferences, 1)
    assert p is not None
    assert p.liked_genres == ["rpg", "puzzle"]
    assert p.disliked_genres == ["horror"]


def test_game_embedding_unique_per_model(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(
        GameEmbedding(
            game_id=game.id, model_name="all-MiniLM-L6-v2", dim=384, embedding=b"\x00" * 8
        )
    )
    db_session.commit()
    db_session.add(
        GameEmbedding(
            game_id=game.id, model_name="all-MiniLM-L6-v2", dim=384, embedding=b"\x01" * 8
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_recommendation_event_writes(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(
        RecommendationEvent(
            game_id=game.id,
            surface="for_you",
            rank=1,
            score=0.87,
            reason_codes=["HIGH_CRITIC_SCORE", "MATCHES_LIKED_GENRE:rpg"],
            model_version="heuristic-v0",
            feature_hash="abc123",
            filters_applied={"price_cap": 30},
            abstention_path="heuristic",
            explanation_variant="templated",
        )
    )
    db_session.commit()
    row = db_session.query(RecommendationEvent).one()
    assert row.reason_codes == ["HIGH_CRITIC_SCORE", "MATCHES_LIKED_GENRE:rpg"]
    assert row.filters_applied == {"price_cap": 30}


def test_remaining_spine_tables_accept_writes(db_session: Session) -> None:
    """Smoke test for the tables not covered above."""
    game = _make_game(db_session)
    db_session.add(GameTag(game_id=game.id, tag="metroidvania", kind="genre"))
    db_session.add(UserGameState(game_id=game.id, status="backlog"))
    db_session.add(
        DataSyncRun(
            source="steam", status="ok", counts={"added": 12}, finished_at=datetime.utcnow()
        )
    )
    db_session.add(LLMCache(prompt_hash="deadbeef", response_json={"text": "hi"}))
    db_session.commit()

    assert db_session.query(GameTag).count() == 1
    assert db_session.query(UserGameState).count() == 1
    assert db_session.query(DataSyncRun).count() == 1
    assert db_session.query(LLMCache).count() == 1

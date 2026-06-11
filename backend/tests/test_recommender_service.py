from sqlalchemy.orm import Session

from app.db.repositories import (
    GameRepository,
    GameTagRepository,
    LibraryEntryRepository,
    PreferencesRepository,
    RecommendationEventRepository,
)
from app.services.recommender_service import (
    OwnedLibraryCandidateSource,
    RecommenderService,
)


def _seed_owned(db_session: Session, *, igdb_id, appid, name, slug, hours, genres):
    g = GameRepository(db_session).upsert(
        igdb_id=igdb_id, steam_appid=appid, name=name, slug=slug, critic_score=85.0
    )
    db_session.commit()
    LibraryEntryRepository(db_session).upsert(
        game_id=g.id, source="steam", external_id=str(appid), hours_played=hours
    )
    GameTagRepository(db_session).replace_tags(game_id=g.id, kind="genre", tags=genres)
    db_session.commit()
    return g


def _service(db_session: Session) -> RecommenderService:
    return RecommenderService(
        candidate_source=OwnedLibraryCandidateSource(
            library=LibraryEntryRepository(db_session),
            tags=GameTagRepository(db_session),
        ),
        preferences=PreferencesRepository(db_session),
        events=RecommendationEventRepository(db_session),
    )


def test_recommend_ranks_and_logs_impressions(db_session: Session) -> None:
    _seed_owned(
        db_session, igdb_id=1, appid=10, name="RPGGame", slug="rpg", hours=0.0, genres=["RPG"]
    )
    _seed_owned(
        db_session,
        igdb_id=2, appid=20, name="SportsGame", slug="sport", hours=50.0, genres=["Sports"],
    )
    PreferencesRepository(db_session).update(
        liked_genres=["RPG"], disliked_genres=[], liked_types=[],
        session_length_pref="any", difficulty_pref="any",
    )
    db_session.commit()

    recs = _service(db_session).recommend(limit=10)
    db_session.commit()

    assert [r.slug for r in recs] == ["rpg", "sport"]
    assert recs[0].event_id is not None
    assert "MATCHES_LIKED_GENRE:RPG" in recs[0].reason_codes
    assert recs[0].explanation.startswith("Recommended because it")
    assert recs[0].model_version == "heuristic-v0"

    # One impression row per returned card.
    from app.db.models import RecommendationEvent
    count = db_session.query(RecommendationEvent).count()
    assert count == 2


def test_recommend_respects_limit(db_session: Session) -> None:
    for i in range(5):
        _seed_owned(
            db_session,
            igdb_id=i + 1, appid=10 + i, name=f"G{i}", slug=f"g{i}", hours=0.0, genres=["RPG"],
        )
    recs = _service(db_session).recommend(limit=3)
    db_session.commit()
    assert len(recs) == 3


def test_recommend_empty_library_returns_empty(db_session: Session) -> None:
    recs = _service(db_session).recommend(limit=10)
    assert recs == []

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.db.repositories import (
    GameRepository,
    GameTagRepository,
    LibraryEntryRepository,
    PreferencesRepository,
)
from app.main import create_app


def _client(db_session: Session) -> TestClient:
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[deps.get_db_session] = _override
    return TestClient(app)


def _seed(db_session: Session) -> None:
    g = GameRepository(db_session).upsert(
        igdb_id=1, steam_appid=10, name="RPGGame", slug="rpg", critic_score=90.0
    )
    db_session.commit()
    LibraryEntryRepository(db_session).upsert(
        game_id=g.id, source="steam", external_id="10", hours_played=0.0
    )
    GameTagRepository(db_session).replace_tags(game_id=g.id, kind="genre", tags=["RPG"])
    PreferencesRepository(db_session).update(
        liked_genres=["RPG"], disliked_genres=[], liked_types=[],
        session_length_pref="any", difficulty_pref="any",
    )
    db_session.commit()


def test_for_you_returns_items_and_logs_impressions(db_session: Session) -> None:
    _seed(db_session)
    res = _client(db_session).get("/api/for-you")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["slug"] == "rpg"
    assert item["event_id"] is not None
    assert "MATCHES_LIKED_GENRE:RPG" in item["reason_codes"]
    assert item["explanation"].startswith("Recommended because it")

    from app.db.models import RecommendationEvent
    assert db_session.query(RecommendationEvent).count() == 1


def test_click_marks_event(db_session: Session) -> None:
    _seed(db_session)
    client = _client(db_session)
    eid = client.get("/api/for-you").json()["items"][0]["event_id"]
    assert client.post(f"/api/recommendations/{eid}/click").status_code == 200
    assert client.post("/api/recommendations/99999/click").status_code == 404


def test_dismiss_validates_reason(db_session: Session) -> None:
    _seed(db_session)
    client = _client(db_session)
    eid = client.get("/api/for-you").json()["items"][0]["event_id"]
    assert client.post(
        f"/api/recommendations/{eid}/dismiss", json={"reason": "too_long"}
    ).status_code == 200
    assert client.post(
        f"/api/recommendations/{eid}/dismiss", json={"reason": "nonsense"}
    ).status_code == 422


def test_start_playing_sets_status(db_session: Session) -> None:
    _seed(db_session)
    client = _client(db_session)
    item = client.get("/api/for-you").json()["items"][0]
    res = client.post(f"/api/recommendations/{item['event_id']}/start-playing")
    assert res.status_code == 200
    # Status now reflected on the library listing.
    lib = client.get("/api/library").json()
    row = [x for x in lib if x["game_id"] == item["game_id"]][0]
    assert row["status"] == "currently_playing"
    assert client.post("/api/recommendations/99999/start-playing").status_code == 404

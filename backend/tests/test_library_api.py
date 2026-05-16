from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import library as library_api
from app.db.repositories import GameRepository, LibraryEntryRepository, SyncRunRepository
from app.main import create_app
from app.services.library_sync import SyncOutcome


def _make_client_with_session(db_session: Session) -> TestClient:
    """Builds a TestClient with the DB dependency overridden to use db_session."""
    app = create_app()

    def _override_session():
        yield db_session

    app.dependency_overrides[library_api.get_db_session] = _override_session
    return TestClient(app)


def test_get_library_returns_owned_games(db_session: Session) -> None:
    g = GameRepository(db_session).upsert(
        igdb_id=1,
        steam_appid=10,
        name="Half-Life 2",
        slug="half-life-2",
        critic_score=96.0,
    )
    db_session.commit()
    LibraryEntryRepository(db_session).upsert(
        game_id=g.id, source="steam", external_id="10", hours_played=12.5
    )
    db_session.commit()

    client = _make_client_with_session(db_session)
    res = client.get("/api/library")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    item = body[0]
    assert item["name"] == "Half-Life 2"
    assert item["steam_appid"] == 10
    assert item["hours_played"] == 12.5
    assert item["critic_score"] == 96.0


def test_get_sync_runs_returns_recent_descending(db_session: Session) -> None:
    repo = SyncRunRepository(db_session)
    a = repo.start("steam")
    db_session.commit()
    repo.finish(a, status="ok", counts={"added": 5}, error=None)
    db_session.commit()

    client = _make_client_with_session(db_session)
    res = client.get("/api/library/sync-runs")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["source"] == "steam"
    assert body[0]["status"] == "ok"
    assert body[0]["counts"] == {"added": 5}


def test_post_sync_steam_invokes_service_and_returns_outcome(
    db_session: Session, monkeypatch
) -> None:
    fake_outcome = SyncOutcome(
        run_id=42,
        status="ok",
        counts={"added": 7, "updated": 0, "unmatched_igdb": 0},
    )

    captured = {}

    class FakeService:
        def __init__(self, **_kwargs) -> None:
            pass

        def sync_steam(self, *, steam_id: str) -> SyncOutcome:
            captured["steam_id"] = steam_id
            return fake_outcome

    monkeypatch.setattr(
        library_api, "_build_sync_service", lambda session: FakeService()
    )

    client = _make_client_with_session(db_session)
    res = client.post(
        "/api/library/sync/steam",
        json={"steam_id": "76561198000000000"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "run_id": 42,
        "status": "ok",
        "counts": {"added": 7, "updated": 0, "unmatched_igdb": 0},
        "error": None,
    }
    assert captured["steam_id"] == "76561198000000000"


def test_post_sync_steam_uses_settings_steam_id_when_omitted(
    db_session: Session, monkeypatch
) -> None:
    captured = {}

    class FakeService:
        def __init__(self, **_kwargs) -> None:
            pass

        def sync_steam(self, *, steam_id: str) -> SyncOutcome:
            captured["steam_id"] = steam_id
            return SyncOutcome(run_id=1, status="ok", counts={})

    monkeypatch.setattr(
        library_api, "_build_sync_service", lambda session: FakeService()
    )
    monkeypatch.setattr(library_api.settings, "steam_user_id", "76561198999999999")

    client = _make_client_with_session(db_session)
    res = client.post("/api/library/sync/steam", json={})
    assert res.status_code == 200
    assert captured["steam_id"] == "76561198999999999"


def test_post_sync_steam_returns_400_when_no_id_anywhere(
    db_session: Session, monkeypatch
) -> None:
    monkeypatch.setattr(library_api.settings, "steam_user_id", "")
    client = _make_client_with_session(db_session)
    res = client.post("/api/library/sync/steam", json={})
    assert res.status_code == 400
    assert "steam id" in res.json()["detail"].lower()

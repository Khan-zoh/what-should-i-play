from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.main import create_app


def _client(db_session: Session) -> TestClient:
    app = create_app()

    def _override():
        yield db_session

    # Every router depends on the single shared deps.get_db_session, so one
    # override covers all routes.
    app.dependency_overrides[deps.get_db_session] = _override
    return TestClient(app)


def test_get_preferences_returns_defaults(db_session: Session) -> None:
    res = _client(db_session).get("/api/preferences")
    assert res.status_code == 200
    body = res.json()
    assert body["liked_genres"] == []
    assert body["session_length_pref"] == "any"


def test_put_preferences_persists(db_session: Session) -> None:
    client = _client(db_session)
    res = client.put(
        "/api/preferences",
        json={
            "liked_genres": ["RPG"],
            "disliked_genres": ["Sports"],
            "liked_types": ["singleplayer"],
            "session_length_pref": "short",
            "difficulty_pref": "any",
        },
    )
    assert res.status_code == 200
    assert res.json()["liked_genres"] == ["RPG"]
    # Persisted across requests.
    assert client.get("/api/preferences").json()["disliked_genres"] == ["Sports"]

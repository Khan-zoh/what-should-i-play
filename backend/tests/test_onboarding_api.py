from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.main import create_app


def _client(db_session: Session) -> TestClient:
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[deps.get_db_session] = _override
    return TestClient(app)


def test_get_onboarding_defaults_false(db_session: Session) -> None:
    res = _client(db_session).get("/api/onboarding")
    assert res.status_code == 200
    assert res.json() == {"completed": False}


def test_put_onboarding_persists(db_session: Session) -> None:
    client = _client(db_session)
    res = client.put("/api/onboarding", json={"completed": True})
    assert res.status_code == 200
    assert res.json() == {"completed": True}
    assert client.get("/api/onboarding").json() == {"completed": True}


def test_saving_preferences_does_not_reset_onboarding(db_session: Session) -> None:
    client = _client(db_session)
    client.put("/api/onboarding", json={"completed": True})
    client.put(
        "/api/preferences",
        json={
            "liked_genres": ["RPG"],
            "disliked_genres": [],
            "liked_types": [],
            "session_length_pref": "any",
            "difficulty_pref": "any",
        },
    )
    assert client.get("/api/onboarding").json() == {"completed": True}

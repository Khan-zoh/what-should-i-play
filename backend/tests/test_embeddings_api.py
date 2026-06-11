import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.api import embeddings as embeddings_api
from app.db.repositories import (
    GameRepository,
    GameTagRepository,
    LibraryEntryRepository,
)
from app.main import create_app


class FakeEncoder:
    def encode(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 3), dtype=np.float32)


def _client(db_session: Session, monkeypatch) -> TestClient:
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[deps.get_db_session] = _override
    monkeypatch.setattr(embeddings_api, "_build_encoder", lambda: FakeEncoder())
    return TestClient(app)


def _seed(db_session: Session) -> None:
    g = GameRepository(db_session).upsert(
        igdb_id=1, steam_appid=10, name="A", slug="a", summary="s"
    )
    db_session.commit()
    LibraryEntryRepository(db_session).upsert(
        game_id=g.id, source="steam", external_id="10", hours_played=1.0
    )
    GameTagRepository(db_session).replace_tags(game_id=g.id, kind="genre", tags=["RPG"])
    db_session.commit()


def test_rebuild_embeds_missing_and_reports(db_session: Session, monkeypatch) -> None:
    _seed(db_session)
    client = _client(db_session, monkeypatch)

    res = client.post("/api/embeddings/rebuild")
    assert res.status_code == 200
    body = res.json()
    assert body["attempted"] == 1
    assert body["embedded"] == 1
    assert body["failed"] == []

    # Second call: nothing to do.
    res2 = client.post("/api/embeddings/rebuild")
    assert res2.json()["attempted"] == 0
    assert res2.json()["skipped_existing"] == 1

    # Force re-embeds.
    res3 = client.post("/api/embeddings/rebuild?force=true")
    assert res3.json()["embedded"] == 1


def test_rebuild_reports_encoder_unavailable(db_session: Session, monkeypatch) -> None:
    _seed(db_session)
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[deps.get_db_session] = _override

    def _boom():
        raise RuntimeError("sentence-transformers is not installed. pip install -e .[ml]")

    monkeypatch.setattr(embeddings_api, "_build_encoder", _boom)
    client = TestClient(app)

    res = client.post("/api/embeddings/rebuild")
    assert res.status_code == 503
    assert "pip install" in res.json()["detail"]

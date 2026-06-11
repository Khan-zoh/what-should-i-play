import sys

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.db.repositories import (
    GameEmbeddingRepository,
    GameRepository,
    GameTagRepository,
    LibraryEntryRepository,
)
from app.services.embedding_service import (
    EmbeddingService,
    build_input_text,
    embedding_revision,
    load_real_encoder,
)


class FakeEncoder:
    """Deterministic stand-in: vector = [len(text), #commas, 1] normalized-ish."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls.append(texts)
        return np.array(
            [[float(len(t)), float(t.count(",")), 1.0] for t in texts],
            dtype=np.float32,
        )


def _seed(db_session: Session, *, igdb_id: int, appid: int, name: str, slug: str):
    g = GameRepository(db_session).upsert(
        igdb_id=igdb_id, steam_appid=appid, name=name, slug=slug, summary="fun game"
    )
    db_session.commit()
    LibraryEntryRepository(db_session).upsert(
        game_id=g.id, source="steam", external_id=str(appid), hours_played=1.0
    )
    GameTagRepository(db_session).replace_tags(game_id=g.id, kind="genre", tags=["RPG"])
    db_session.commit()
    return g


def _service(db_session: Session, encoder: FakeEncoder) -> EmbeddingService:
    return EmbeddingService(
        encoder=encoder,
        model_name="fake-model",
        library=LibraryEntryRepository(db_session),
        tags=GameTagRepository(db_session),
        embeddings=GameEmbeddingRepository(db_session),
    )


def test_build_input_text_pins_template() -> None:
    text = build_input_text(
        name="Hollow Knight", summary="A 2D adventure.", tags=["Platform", "Fantasy"]
    )
    assert text == "Hollow Knight - A 2D adventure. | tags: Fantasy, Platform"


def test_build_input_text_handles_missing_summary_and_tags() -> None:
    assert build_input_text(name="X", summary=None, tags=[]) == "X -  | tags: "


def test_embedding_revision_composite_key() -> None:
    rev = embedding_revision("sentence-transformers/all-MiniLM-L6-v2")
    assert rev == "all-MiniLM-L6-v2|t1"


def test_embed_missing_embeds_only_missing(db_session: Session) -> None:
    a = _seed(db_session, igdb_id=1, appid=10, name="A", slug="a")
    b = _seed(db_session, igdb_id=2, appid=20, name="B", slug="b")
    encoder = FakeEncoder()
    service = _service(db_session, encoder)
    rev = embedding_revision("fake-model")

    report = service.embed_missing()
    db_session.commit()
    assert report.model == rev
    assert report.attempted == 2
    assert report.embedded == 2
    assert report.skipped_existing == 0
    assert report.failed == []
    assert set(GameEmbeddingRepository(db_session).get_all(model_name=rev)) == {a.id, b.id}

    # Second run: nothing missing.
    report2 = service.embed_missing()
    assert report2.attempted == 0
    assert report2.skipped_existing == 2

    # Force re-embeds everything.
    report3 = service.embed_missing(force=True)
    assert report3.attempted == 2
    assert report3.embedded == 2


def test_embed_missing_reports_encoder_failure(db_session: Session) -> None:
    _seed(db_session, igdb_id=1, appid=10, name="A", slug="a")

    class BoomEncoder:
        def encode(self, texts: list[str]) -> np.ndarray:
            raise RuntimeError("model exploded")

    service = EmbeddingService(
        encoder=BoomEncoder(),
        model_name="fake-model",
        library=LibraryEntryRepository(db_session),
        tags=GameTagRepository(db_session),
        embeddings=GameEmbeddingRepository(db_session),
    )
    report = service.embed_missing()
    assert report.embedded == 0
    assert len(report.failed) == 1
    assert "model exploded" in report.failed[0]["error"]


def test_load_real_encoder_clear_error_when_extra_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match=r"pip install -e \.\[ml\]"):
        load_real_encoder("sentence-transformers/all-MiniLM-L6-v2")


@pytest.mark.ml
def test_real_encoder_contract() -> None:
    st = pytest.importorskip("sentence_transformers")
    assert st is not None
    encoder = load_real_encoder("sentence-transformers/all-MiniLM-L6-v2")
    out = encoder.encode(["hello world", "hello world"])
    assert out.shape == (2, 384)
    assert out.dtype == np.float32
    # Same text at different batch positions differs at ~1e-8 (CPU matmul
    # reduction order). The contract that matters downstream is cosine-level
    # stability, so assert near-equality with an explicit tolerance.
    assert np.allclose(out[0], out[1], atol=1e-5)
    assert abs(float(np.linalg.norm(out[0])) - 1.0) < 1e-3  # L2-normalized

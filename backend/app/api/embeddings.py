"""HTTP endpoint for (re)building game content embeddings.

Deliberately separate from the Steam sync: embeddings are an enhancement layer,
and a 503 here (missing [ml] extra) must never affect imports.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import settings
from app.db.repositories import (
    GameEmbeddingRepository,
    GameTagRepository,
    LibraryEntryRepository,
)
from app.services.embedding_service import EmbeddingService, Encoder, load_real_encoder

router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])


class EmbedReportOut(BaseModel):
    model: str
    attempted: int
    embedded: int
    skipped_existing: int
    failed: list[dict]


def _build_encoder() -> Encoder:
    # Broken out so tests can monkeypatch in a fake encoder.
    return load_real_encoder(settings.embedding_model_name)


@router.post("/rebuild", response_model=EmbedReportOut)
def rebuild(
    force: bool = Query(default=False),
    session: Session = Depends(get_db_session),
) -> EmbedReportOut:
    try:
        encoder = _build_encoder()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    service = EmbeddingService(
        encoder=encoder,
        model_name=settings.embedding_model_name,
        library=LibraryEntryRepository(session),
        tags=GameTagRepository(session),
        embeddings=GameEmbeddingRepository(session),
    )
    report = service.embed_missing(force=force)
    session.commit()
    return EmbedReportOut(
        model=report.model,
        attempted=report.attempted,
        embedded=report.embedded,
        skipped_existing=report.skipped_existing,
        failed=report.failed,
    )

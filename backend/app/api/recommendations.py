"""HTTP endpoints for the 'For You' surface and its interaction telemetry."""
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
    PreferencesRepository,
    RecommendationEventRepository,
    UserGameStateRepository,
)
from app.services.embedding_service import embedding_revision
from app.services.recommender_service import (
    OwnedLibraryCandidateSource,
    RecommenderService,
)

router = APIRouter(tags=["recommendations"])

DISMISS_REASONS = frozenset(
    {
        "too_long",
        "wrong_genre",
        "too_expensive",
        "wrong_platform",
        "already_played_elsewhere",
        "not_interested",
    }
)


class ForYouItem(BaseModel):
    event_id: int
    game_id: int
    name: str
    slug: str
    cover_url: str | None
    genres: list[str]
    critic_score: float | None
    hours_played: float
    status: str | None
    reason_codes: list[str]
    explanation: str
    score: float
    model_version: str


class ForYouResponse(BaseModel):
    items: list[ForYouItem]


class DismissRequest(BaseModel):
    reason: str


def _build_recommender(session: Session) -> RecommenderService:
    return RecommenderService(
        candidate_source=OwnedLibraryCandidateSource(
            library=LibraryEntryRepository(session),
            tags=GameTagRepository(session),
        ),
        preferences=PreferencesRepository(session),
        events=RecommendationEventRepository(session),
        embeddings=GameEmbeddingRepository(session),
        embedding_revision=embedding_revision(settings.embedding_model_name),
    )


@router.get("/api/for-you", response_model=ForYouResponse)
def for_you(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> ForYouResponse:
    recs = _build_recommender(session).recommend(limit=limit)
    session.commit()
    return ForYouResponse(
        items=[
            ForYouItem(
                event_id=r.event_id,
                game_id=r.game_id,
                name=r.name,
                slug=r.slug,
                cover_url=r.cover_url,
                genres=r.genres,
                critic_score=r.critic_score,
                hours_played=r.hours_played,
                status=r.status,
                reason_codes=r.reason_codes,
                explanation=r.explanation,
                score=r.score,
                model_version=r.model_version,
            )
            for r in recs
        ]
    )


@router.post("/api/recommendations/{event_id}/click")
def click(event_id: int, session: Session = Depends(get_db_session)) -> dict:
    if not RecommendationEventRepository(session).mark_clicked(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    session.commit()
    return {"ok": True}


@router.post("/api/recommendations/{event_id}/dismiss")
def dismiss(
    event_id: int,
    body: DismissRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    if body.reason not in DISMISS_REASONS:
        raise HTTPException(status_code=422, detail=f"Invalid reason: {body.reason}")
    if not RecommendationEventRepository(session).mark_dismissed(event_id, body.reason):
        raise HTTPException(status_code=404, detail="Event not found")
    session.commit()
    return {"ok": True}


@router.post("/api/recommendations/{event_id}/start-playing")
def start_playing(
    event_id: int, session: Session = Depends(get_db_session)
) -> dict:
    events = RecommendationEventRepository(session)
    ev = events.mark_started_playing(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    UserGameStateRepository(session).set_status(
        game_id=ev.game_id, status="currently_playing"
    )
    session.commit()
    return {"ok": True, "status": "currently_playing"}

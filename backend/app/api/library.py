"""HTTP endpoints for library viewing and sync triggering.

Routes are intentionally thin: parse input, call a service or repository,
return JSON. All ORM work happens through the repository layer.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import settings
from app.db.models import VALID_GAME_STATUSES
from app.db.repositories import (
    GameRepository,
    LibraryEntryRepository,
    RatingRepository,
    SyncRunRepository,
    UserGameStateRepository,
)
from app.services.igdb_client import IgdbAuth, IgdbClient
from app.services.library_sync import LibrarySyncService, SyncOutcome
from app.services.steam_client import SteamClient

router = APIRouter(prefix="/api/library", tags=["library"])


# ---------------------------------------------------------------------------
# Pydantic response/request models
# ---------------------------------------------------------------------------


class LibraryItem(BaseModel):
    game_id: int
    name: str
    slug: str
    steam_appid: int | None
    igdb_id: int | None
    hours_played: float
    cover_url: str | None
    critic_score: float | None
    store_url: str | None
    enjoyment: int | None
    status: str | None


class SyncRunOut(BaseModel):
    id: int
    source: str
    status: str
    started_at: str
    finished_at: str | None
    counts: dict
    error: str | None


class SyncSteamRequest(BaseModel):
    steam_id: str | None = None


class SyncOutcomeOut(BaseModel):
    run_id: int
    status: str
    counts: dict
    error: str | None
    error_code: str | None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[LibraryItem])
def list_library(session: Session = Depends(get_db_session)) -> list[LibraryItem]:
    rows = LibraryEntryRepository(session).list_with_user_data()
    return [
        LibraryItem(
            game_id=g.id,
            name=g.name,
            slug=g.slug,
            steam_appid=g.steam_appid,
            igdb_id=g.igdb_id,
            hours_played=entry.hours_played,
            cover_url=g.cover_url,
            critic_score=g.critic_score,
            store_url=g.store_url,
            enjoyment=rating.enjoyment if rating else None,
            status=state.status if state else None,
        )
        for entry, g, rating, state in rows
    ]


@router.get("/sync-runs", response_model=list[SyncRunOut])
def list_sync_runs(session: Session = Depends(get_db_session)) -> list[SyncRunOut]:
    rows = SyncRunRepository(session).list_recent(limit=20)
    return [
        SyncRunOut(
            id=r.id,
            source=r.source,
            status=r.status,
            started_at=r.started_at.isoformat(),
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
            counts=r.counts,
            error=r.error,
        )
        for r in rows
    ]


@router.post("/sync/steam", response_model=SyncOutcomeOut)
def sync_steam(
    body: SyncSteamRequest,
    session: Session = Depends(get_db_session),
) -> SyncOutcomeOut:
    steam_id = body.steam_id or settings.steam_user_id
    if not steam_id:
        raise HTTPException(
            status_code=400,
            detail="No Steam ID provided in request and STEAM_USER_ID is not set.",
        )

    service = _build_sync_service(session)
    outcome: SyncOutcome = service.sync_steam(steam_id=steam_id)
    return SyncOutcomeOut(
        run_id=outcome.run_id,
        status=outcome.status,
        counts=outcome.counts,
        error=outcome.error,
        error_code=outcome.error_code,
    )


class RatingRequest(BaseModel):
    enjoyment: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


class RatingOut(BaseModel):
    game_id: int
    enjoyment: int | None
    notes: str | None


class StatusRequest(BaseModel):
    status: str | None = None


class StatusOut(BaseModel):
    game_id: int
    status: str | None


def _require_game(session: Session, game_id: int) -> None:
    if GameRepository(session).get(game_id) is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")


@router.post("/games/{game_id}/rating", response_model=RatingOut)
def set_rating(
    game_id: int,
    body: RatingRequest,
    session: Session = Depends(get_db_session),
) -> RatingOut:
    _require_game(session, game_id)
    repo = RatingRepository(session)
    if body.enjoyment is None:
        repo.delete(game_id=game_id)
        session.commit()
        return RatingOut(game_id=game_id, enjoyment=None, notes=None)
    rating = repo.upsert(game_id=game_id, enjoyment=body.enjoyment, notes=body.notes)
    session.commit()
    return RatingOut(game_id=game_id, enjoyment=rating.enjoyment, notes=rating.notes)


@router.put("/games/{game_id}/status", response_model=StatusOut)
def set_status(
    game_id: int,
    body: StatusRequest,
    session: Session = Depends(get_db_session),
) -> StatusOut:
    _require_game(session, game_id)
    repo = UserGameStateRepository(session)
    if body.status is None:
        repo.clear(game_id=game_id)
        session.commit()
        return StatusOut(game_id=game_id, status=None)
    if body.status not in VALID_GAME_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")
    state = repo.set_status(game_id=game_id, status=body.status)
    session.commit()
    return StatusOut(game_id=game_id, status=state.status)


# ---------------------------------------------------------------------------
# Service factory - broken out so tests can monkeypatch it.
# ---------------------------------------------------------------------------


def _build_sync_service(session: Session) -> LibrarySyncService:
    steam = SteamClient(
        api_key=settings.steam_api_key,
        timeout_seconds=settings.http_timeout_seconds,
    )
    igdb_auth = IgdbAuth(
        client_id=settings.igdb_client_id,
        client_secret=settings.igdb_client_secret,
        timeout_seconds=settings.http_timeout_seconds,
    )
    igdb = IgdbClient(
        igdb_auth,
        client_id=settings.igdb_client_id,
        timeout_seconds=settings.http_timeout_seconds,
    )
    return LibrarySyncService(
        steam_client=steam,
        igdb_client=igdb,
        games=GameRepository(session),
        library=LibraryEntryRepository(session),
        sync_runs=SyncRunRepository(session),
        session=session,
    )

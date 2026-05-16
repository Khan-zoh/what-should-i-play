"""HTTP endpoints for library viewing and sync triggering.

Routes are intentionally thin: parse input, call a service or repository,
return JSON. All ORM work happens through the repository layer.
"""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.repositories import (
    GameRepository,
    LibraryEntryRepository,
    SyncRunRepository,
)
from app.db.session import SessionLocal
from app.services.igdb_client import IgdbAuth, IgdbClient
from app.services.library_sync import LibrarySyncService, SyncOutcome
from app.services.steam_client import SteamClient

router = APIRouter(prefix="/api/library", tags=["library"])


# ---------------------------------------------------------------------------
# DB session dependency. Defined here (not imported from app.db.session.get_db)
# so tests can override it cleanly via app.dependency_overrides.
# ---------------------------------------------------------------------------


def get_db_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[LibraryItem])
def list_library(session: Session = Depends(get_db_session)) -> list[LibraryItem]:  # noqa: B008
    rows = LibraryEntryRepository(session).list_all_with_games()
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
        )
        for entry, g in rows
    ]


@router.get("/sync-runs", response_model=list[SyncRunOut])
def list_sync_runs(session: Session = Depends(get_db_session)) -> list[SyncRunOut]:  # noqa: B008
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
    session: Session = Depends(get_db_session),  # noqa: B008
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
    )


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

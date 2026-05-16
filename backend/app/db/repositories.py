"""Repository layer: the only place outside models.py that touches SQLAlchemy ORM.

Services receive repository instances, not Sessions, so service code stays free
of ORM imports and is easy to unit-test with fakes.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import DataSyncRun, Game, LibraryEntry


class GameRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        igdb_id: int | None,
        steam_appid: int | None,
        name: str,
        slug: str,
        summary: str | None = None,
        cover_url: str | None = None,
        store_url: str | None = None,
        critic_score: float | None = None,
        steam_review_score: float | None = None,
        steam_review_count: int | None = None,
        price_usd: float | None = None,
        release_year: int | None = None,
    ) -> Game:
        existing: Game | None = None
        if igdb_id is not None:
            existing = self._session.scalar(select(Game).where(Game.igdb_id == igdb_id))
        if existing is None and steam_appid is not None:
            existing = self._session.scalar(
                select(Game).where(Game.steam_appid == steam_appid)
            )

        if existing is None:
            existing = Game(name=name, slug=slug)
            self._session.add(existing)

        # Apply non-None fields. None means "leave the existing value alone".
        for field_name, value in [
            ("igdb_id", igdb_id),
            ("steam_appid", steam_appid),
            ("name", name),
            ("slug", slug),
            ("summary", summary),
            ("cover_url", cover_url),
            ("store_url", store_url),
            ("critic_score", critic_score),
            ("steam_review_score", steam_review_score),
            ("steam_review_count", steam_review_count),
            ("price_usd", price_usd),
            ("release_year", release_year),
        ]:
            if value is not None:
                setattr(existing, field_name, value)

        self._session.flush()
        return existing


class LibraryEntryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        game_id: int,
        source: str,
        external_id: str | None,
        hours_played: float,
        acquired_at: datetime | None = None,
    ) -> LibraryEntry:
        existing = self._session.scalar(
            select(LibraryEntry).where(LibraryEntry.game_id == game_id)
        )
        if existing is None:
            existing = LibraryEntry(
                game_id=game_id, source=source, hours_played=hours_played
            )
            self._session.add(existing)

        existing.source = source
        existing.external_id = external_id
        existing.hours_played = hours_played
        if acquired_at is not None:
            existing.acquired_at = acquired_at

        self._session.flush()
        return existing

    def list_all_with_games(self) -> list[tuple[LibraryEntry, Game]]:
        rows = self._session.execute(
            select(LibraryEntry, Game).join(Game, Game.id == LibraryEntry.game_id)
        ).all()
        return [(le, g) for le, g in rows]


class SyncRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start(self, source: str) -> DataSyncRun:
        run = DataSyncRun(source=source, status="ok", counts={})
        self._session.add(run)
        self._session.flush()
        return run

    def finish(
        self,
        run: DataSyncRun,
        *,
        status: str,
        counts: dict,
        error: str | None,
    ) -> None:
        run.status = status
        run.counts = counts
        run.error = error
        run.finished_at = datetime.utcnow()
        self._session.flush()

    def list_recent(self, limit: int = 20) -> list[DataSyncRun]:
        rows = self._session.scalars(
            select(DataSyncRun).order_by(desc(DataSyncRun.started_at)).limit(limit)
        ).all()
        return list(rows)

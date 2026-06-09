"""Repository layer: the only place outside models.py that touches SQLAlchemy ORM.

Services receive repository instances, not Sessions, so service code stays free
of ORM imports and is easy to unit-test with fakes.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    DataSyncRun,
    Game,
    GameTag,
    LibraryEntry,
    Preferences,
    Rating,
    UserGameState,
)


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

    def get(self, game_id: int) -> Game | None:
        return self._session.get(Game, game_id)


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

    def list_with_user_data(
        self,
    ) -> list[tuple[LibraryEntry, Game, Rating | None, UserGameState | None]]:
        rows = self._session.execute(
            select(LibraryEntry, Game, Rating, UserGameState)
            .join(Game, Game.id == LibraryEntry.game_id)
            .outerjoin(Rating, Rating.game_id == Game.id)
            .outerjoin(UserGameState, UserGameState.game_id == Game.id)
        ).all()
        return [(le, g, r, s) for le, g, r, s in rows]


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


class RatingRepository:
    # Note: `enjoyment` is intentionally nullable at the repo level — a future
    # notes-only / finished-only row is valid. The "Haven't played = no row"
    # product invariant is enforced at the API layer (delete on null), not here.
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, *, game_id: int) -> Rating | None:
        return self._session.scalar(select(Rating).where(Rating.game_id == game_id))

    def upsert(
        self,
        *,
        game_id: int,
        enjoyment: int | None,
        notes: str | None = None,
        finished: bool | None = None,
    ) -> Rating:
        existing = self.get(game_id=game_id)
        if existing is None:
            existing = Rating(game_id=game_id)
            self._session.add(existing)
        existing.enjoyment = enjoyment
        existing.notes = notes
        existing.finished = finished
        self._session.flush()
        return existing

    def delete(self, *, game_id: int) -> bool:
        existing = self.get(game_id=game_id)
        if existing is None:
            return False
        self._session.delete(existing)
        self._session.flush()
        return True


class UserGameStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, *, game_id: int) -> UserGameState | None:
        return self._session.get(UserGameState, game_id)

    def set_status(self, *, game_id: int, status: str) -> UserGameState:
        existing = self.get(game_id=game_id)
        if existing is None:
            existing = UserGameState(game_id=game_id, status=status)
            self._session.add(existing)
        existing.status = status
        self._session.flush()
        return existing

    def clear(self, *, game_id: int) -> bool:
        existing = self.get(game_id=game_id)
        if existing is None:
            return False
        self._session.delete(existing)
        self._session.flush()
        return True


class PreferencesRepository:
    _SINGLETON_ID = 1

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(self) -> Preferences:
        existing = self._session.get(Preferences, self._SINGLETON_ID)
        if existing is None:
            existing = Preferences(id=self._SINGLETON_ID)
            self._session.add(existing)
            self._session.flush()
        return existing

    def update(
        self,
        *,
        liked_genres: list[str],
        disliked_genres: list[str],
        liked_types: list[str],
        session_length_pref: str,
        difficulty_pref: str,
    ) -> Preferences:
        prefs = self.get_or_create()
        prefs.liked_genres = liked_genres
        prefs.disliked_genres = disliked_genres
        prefs.liked_types = liked_types
        prefs.session_length_pref = session_length_pref
        prefs.difficulty_pref = difficulty_pref
        self._session.flush()
        return prefs

    def get_onboarding_completed(self) -> bool:
        return self.get_or_create().onboarding_completed

    def set_onboarding_completed(self, value: bool) -> None:
        prefs = self.get_or_create()
        prefs.onboarding_completed = value
        self._session.flush()


class GameTagRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_tags(self, *, game_id: int, kind: str, tags: list[str]) -> None:
        self._session.execute(
            delete(GameTag).where(GameTag.game_id == game_id, GameTag.kind == kind)
        )
        for tag in dict.fromkeys(tags):  # de-dupe, preserve order
            self._session.add(GameTag(game_id=game_id, kind=kind, tag=tag))
        self._session.flush()

    def genres_for(self, game_id: int) -> set[str]:
        rows = self._session.scalars(
            select(GameTag.tag).where(
                GameTag.game_id == game_id, GameTag.kind == "genre"
            )
        ).all()
        return set(rows)

    def tags_by_game(self, game_ids: list[int]) -> dict[int, dict[str, set[str]]]:
        result: dict[int, dict[str, set[str]]] = {gid: {} for gid in game_ids}
        if not game_ids:
            return result
        rows = self._session.scalars(
            select(GameTag).where(GameTag.game_id.in_(game_ids))
        ).all()
        for t in rows:
            result.setdefault(t.game_id, {}).setdefault(t.kind, set()).add(t.tag)
        return result

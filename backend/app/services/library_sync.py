"""Orchestrates a Steam library import: Steam -> IGDB -> repositories.

This is the only service that knows about all three. Steam and IGDB clients
remain ignorant of each other and of the database.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.repositories import (
    GameRepository,
    LibraryEntryRepository,
    SyncRunRepository,
)
from app.services.igdb_client import IgdbClient, IgdbGame
from app.services.steam_client import (
    InvalidSteamIdError,
    PrivateProfileError,
    SteamAuthError,
    SteamClient,
    SteamClientError,
    SteamGame,
    SteamRateLimitError,
)


@dataclass(frozen=True)
class SyncOutcome:
    run_id: int
    status: str  # "ok" | "partial" | "failed"
    counts: dict = field(default_factory=dict)
    error: str | None = None
    error_code: str | None = None


def _error_code_for(exc: SteamClientError) -> str:
    if isinstance(exc, PrivateProfileError):
        return "private_profile"
    if isinstance(exc, SteamAuthError):
        return "steam_auth"
    if isinstance(exc, SteamRateLimitError):
        return "rate_limited"
    if isinstance(exc, InvalidSteamIdError):
        return "invalid_steamid"
    return "steam_error"


def _slugify_steam(appid: int, name: str) -> str:
    """Cheap deterministic slug for games we can't match in IGDB."""
    safe = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    return f"steam-{appid}-{safe}" if safe else f"steam-{appid}"


class LibrarySyncService:
    def __init__(
        self,
        *,
        steam_client: SteamClient,
        igdb_client: IgdbClient,
        games: GameRepository,
        library: LibraryEntryRepository,
        sync_runs: SyncRunRepository,
        session: Session,
    ) -> None:
        self._steam = steam_client
        self._igdb = igdb_client
        self._games = games
        self._library = library
        self._runs = sync_runs
        self._session = session

    def sync_steam(self, *, steam_id: str) -> SyncOutcome:
        run = self._runs.start("steam")
        self._session.commit()

        try:
            steam_result = self._steam.get_owned_games(steam_id)
        except SteamClientError as e:
            code = _error_code_for(e)
            self._runs.finish(run, status="failed", counts={}, error=str(e))
            self._session.commit()
            return SyncOutcome(
                run_id=run.id,
                status="failed",
                counts={},
                error=str(e),
                error_code=code,
            )

        # Snapshot existing library so we can classify each game as added vs
        # updated in O(1) -- avoids an O(n^2) scan for large libraries.
        existing_appids = {
            g.steam_appid
            for _entry, g in self._library.list_all_with_games()
            if g.steam_appid is not None
        }

        added = 0
        updated = 0
        unmatched = 0

        for steam_game in steam_result.games:
            existed_before = steam_game.appid in existing_appids

            igdb_game = self._lookup_igdb(steam_game.appid)
            if igdb_game is None:
                unmatched += 1

            game = self._upsert_game(steam_game, igdb_game)
            self._library.upsert(
                game_id=game.id,
                source="steam",
                external_id=str(steam_game.appid),
                hours_played=steam_game.playtime_minutes / 60.0,
            )

            if existed_before:
                updated += 1
            else:
                added += 1

        self._session.commit()

        status = "partial" if unmatched > 0 else "ok"
        counts = {"added": added, "updated": updated, "unmatched_igdb": unmatched}
        self._runs.finish(run, status=status, counts=counts, error=None)
        self._session.commit()

        return SyncOutcome(run_id=run.id, status=status, counts=counts, error=None)

    # ---- helpers -------------------------------------------------------

    def _lookup_igdb(self, steam_appid: int) -> IgdbGame | None:
        try:
            igdb_id = self._igdb.lookup_by_steam_appid(steam_appid)
        except Exception:
            # IGDB outage shouldn't kill the sync; treat as unmatched.
            return None
        if igdb_id is None:
            return None
        try:
            return self._igdb.get_game(igdb_id)
        except Exception:
            return None

    def _upsert_game(self, steam_game: SteamGame, igdb_game: IgdbGame | None):
        if igdb_game is None:
            return self._games.upsert(
                igdb_id=None,
                steam_appid=steam_game.appid,
                name=steam_game.name,
                slug=_slugify_steam(steam_game.appid, steam_game.name),
            )
        return self._games.upsert(
            igdb_id=igdb_game.igdb_id,
            steam_appid=steam_game.appid,
            name=igdb_game.name or steam_game.name,
            slug=igdb_game.slug
            or _slugify_steam(steam_game.appid, steam_game.name),
            summary=igdb_game.summary,
            cover_url=igdb_game.cover_url,
            store_url=f"https://store.steampowered.com/app/{steam_game.appid}/",
            critic_score=igdb_game.critic_score,
            release_year=igdb_game.release_year,
        )

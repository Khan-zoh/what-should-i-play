"""Thin wrapper around Steam's IPlayerService/GetOwnedGames endpoint.

Knows nothing about the database, IGDB, or FastAPI. Pure HTTP -> dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

STEAM_BASE = "https://api.steampowered.com"


class SteamClientError(Exception):
    """Base class for all Steam client errors."""


class PrivateProfileError(SteamClientError):
    """Steam returned an empty response, which means the profile is private."""


class InvalidSteamIdError(SteamClientError):
    """Steam returned 5xx, which typically means a malformed steamid."""


class SteamRateLimitError(SteamClientError):
    """Steam returned 429."""


class SteamAuthError(SteamClientError):
    """Steam returned 401/403 — the API key is missing or invalid."""


@dataclass(frozen=True)
class SteamGame:
    appid: int
    name: str
    playtime_minutes: int
    icon_hash: str | None  # for icon URL construction; nullable because Steam sometimes omits it


@dataclass(frozen=True)
class SteamLibraryResult:
    game_count: int
    games: list[SteamGame]


class SteamClient:
    def __init__(self, api_key: str, timeout_seconds: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds

    def get_owned_games(self, steam_id: str) -> SteamLibraryResult:
        url = f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/"
        params = {
            "key": self._api_key,
            "steamid": steam_id,
            "format": "json",
            "include_appinfo": "true",
            "include_played_free_games": "true",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url, params=params)
        except httpx.RequestError as e:
            raise SteamClientError(f"Network error contacting Steam: {e}") from e

        if response.status_code == 429:
            raise SteamRateLimitError("Steam rate limit hit (HTTP 429).")
        if response.status_code in (401, 403):
            raise SteamAuthError(
                f"Steam returned {response.status_code} — API key missing or invalid."
            )
        if response.status_code >= 500:
            raise InvalidSteamIdError(
                f"Steam returned {response.status_code} — usually means an invalid steamid."
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise SteamClientError(f"Steam returned HTTP {response.status_code}.") from e

        payload = response.json().get("response", {})
        if "games" not in payload:
            # No 'games' key. Two cases:
            #  - public profile owning zero games: 'game_count' present and 0 -> success
            #  - private profile / no data: empty {} -> PrivateProfileError
            if payload.get("game_count") == 0:
                return SteamLibraryResult(game_count=0, games=[])
            raise PrivateProfileError(
                "Steam returned no game list — profile is private or account owns no games."
            )

        games = [
            SteamGame(
                appid=int(g["appid"]),
                name=str(g.get("name", "Unknown")),
                playtime_minutes=int(g.get("playtime_forever", 0)),
                icon_hash=g.get("img_icon_url") or None,
            )
            for g in payload["games"]
        ]
        return SteamLibraryResult(
            game_count=int(payload.get("game_count", len(games))),
            games=games,
        )

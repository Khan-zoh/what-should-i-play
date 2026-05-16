"""IGDB API client. Uses Twitch OAuth client_credentials for auth."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_EXTERNAL_URL = "https://api.igdb.com/v4/external_games"
IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
IGDB_COVER_URL_TEMPLATE = (
    "https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"
)

# Refresh the token a minute before it actually expires to avoid edge-case 401s.
_EXPIRATION_SAFETY_SECONDS = 60

# IGDB external_games.external_game_source 1 == Steam.
# (Field was renamed from `category` in a recent IGDB API revision.)
_STEAM_EXTERNAL_SOURCE = 1


class IgdbAuthError(Exception):
    """Raised when Twitch refuses our credentials or returns an unexpected token response."""


class IgdbAuth:
    """Caches a Twitch OAuth bearer token, refreshing it when it expires."""

    def __init__(
        self, client_id: str, client_secret: str, timeout_seconds: float = 10.0
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout_seconds
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def get_token(self) -> str:
        if (
            self._token is not None
            and self._expires_at is not None
            and datetime.utcnow() < self._expires_at
        ):
            return self._token

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                TWITCH_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
            )

        if response.status_code != 200:
            raise IgdbAuthError(
                f"Twitch token endpoint returned {response.status_code}: {response.text}"
            )

        data = response.json()
        token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not token or not isinstance(expires_in, int):
            raise IgdbAuthError(f"Twitch returned malformed token response: {data}")

        self._token = token
        self._expires_at = datetime.utcnow() + timedelta(
            seconds=expires_in - _EXPIRATION_SAFETY_SECONDS
        )
        return token


@dataclass(frozen=True)
class IgdbGame:
    igdb_id: int
    name: str
    slug: str
    summary: str | None = None
    cover_url: str | None = None
    release_year: int | None = None
    critic_score: float | None = None  # IGDB total_rating, 0..100
    critic_score_count: int | None = None
    genres: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    igdb_url: str | None = None


class IgdbClient:
    def __init__(
        self, auth: IgdbAuth, client_id: str, timeout_seconds: float = 10.0
    ) -> None:
        self._auth = auth
        self._client_id = client_id
        self._timeout = timeout_seconds

    def lookup_by_steam_appid(self, steam_appid: int) -> int | None:
        body = (
            "fields game,uid,external_game_source; "
            f"where external_game_source = {_STEAM_EXTERNAL_SOURCE} "
            f'& uid = "{steam_appid}";'
        )
        rows = self._post(IGDB_EXTERNAL_URL, body)
        if not rows:
            return None
        return int(rows[0]["game"])

    def get_game(self, igdb_id: int) -> IgdbGame | None:
        body = (
            "fields name,slug,summary,cover.image_id,genres.name,themes.name,"
            "first_release_date,total_rating,total_rating_count,url;"
            f" where id = {igdb_id};"
        )
        rows = self._post(IGDB_GAMES_URL, body)
        if not rows:
            return None
        return self._parse_game(rows[0])

    def _post(self, url: str, body: str) -> list[dict]:
        token = self._auth.get_token()
        headers = {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "text/plain",
        }
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(url, headers=headers, content=body)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _parse_game(row: dict) -> IgdbGame:
        cover = row.get("cover")
        cover_url = (
            IGDB_COVER_URL_TEMPLATE.format(image_id=cover["image_id"])
            if isinstance(cover, dict) and cover.get("image_id")
            else None
        )

        first_release_date = row.get("first_release_date")
        release_year = (
            datetime.utcfromtimestamp(int(first_release_date)).year
            if first_release_date
            else None
        )

        genres = [
            g["name"]
            for g in row.get("genres") or []
            if isinstance(g, dict) and g.get("name")
        ]
        themes = [
            t["name"]
            for t in row.get("themes") or []
            if isinstance(t, dict) and t.get("name")
        ]

        return IgdbGame(
            igdb_id=int(row["id"]),
            name=str(row.get("name", "Unknown")),
            slug=str(row.get("slug", "")),
            summary=row.get("summary"),
            cover_url=cover_url,
            release_year=release_year,
            critic_score=(
                float(row["total_rating"])
                if row.get("total_rating") is not None
                else None
            ),
            critic_score_count=(
                int(row["total_rating_count"])
                if row.get("total_rating_count") is not None
                else None
            ),
            genres=genres,
            themes=themes,
            igdb_url=row.get("url"),
        )

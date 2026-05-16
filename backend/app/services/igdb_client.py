"""IGDB API client. Uses Twitch OAuth client_credentials for auth.

This file currently contains only the auth helper. The game-lookup methods are
added in Task 4.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

# Refresh the token a minute before it actually expires to avoid edge-case 401s.
_EXPIRATION_SAFETY_SECONDS = 60


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

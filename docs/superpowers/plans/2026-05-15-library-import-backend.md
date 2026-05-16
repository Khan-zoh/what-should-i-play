# Sub-plan 2a — Library Import Backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend infrastructure that imports a Steam library — a Steam Web API client, an IGDB client (with Twitch OAuth), an orchestrating sync service, persistence to `games` / `library_entries` / `data_sync_runs`, and three HTTP endpoints to trigger and inspect syncs. No frontend in this sub-plan; verification is via curl and pytest.

**Architecture:** Three thin service modules in `app/services/` (each has one job: talk to one external system, or orchestrate the others). A repository layer in `app/db/repositories.py` owns all SQLAlchemy reads/writes — services never touch ORM directly. API routes are thin: parse request → call service → return JSON. Tests use `respx` to mock HTTP (no live calls in CI). The plan ends with a manual one-shot smoke test against real Steam + IGDB to confirm the pipeline works end-to-end.

**Tech Stack:**
- Python 3.11+, FastAPI, SQLAlchemy 2 (already in place)
- httpx (sync `Client`, already in deps) for both APIs
- respx (NEW dev dep) for mocking httpx in tests
- pydantic (already there) for request/response models
- Steam Web API: `IPlayerService/GetOwnedGames/v1`
- IGDB v4 (auth via Twitch OAuth `client_credentials`)

---

## File Structure

This sub-plan creates / modifies the following files. Each task says exactly which files it touches.

```
backend/
├── .env.example                          NEW — documents required env vars
├── pyproject.toml                        MODIFY — add respx
├── app/
│   ├── config.py                         MODIFY — add API key + Steam ID fields
│   ├── main.py                           MODIFY — include library router
│   ├── api/
│   │   └── library.py                    NEW — sync + library endpoints
│   ├── services/
│   │   ├── __init__.py                   NEW (empty)
│   │   ├── steam_client.py               NEW — Steam Web API wrapper
│   │   ├── igdb_client.py                NEW — IGDB + Twitch OAuth
│   │   └── library_sync.py               NEW — orchestration
│   └── db/
│       └── repositories.py               NEW — game / library / sync_run repos
└── tests/
    ├── conftest.py                       MODIFY — add respx fixture
    ├── test_steam_client.py              NEW
    ├── test_igdb_client.py               NEW
    ├── test_repositories.py              NEW
    ├── test_library_sync.py              NEW
    └── test_library_api.py               NEW
```

**Per-file responsibilities:**

- `app/services/steam_client.py` — `SteamClient` class. Single method that matters: `get_owned_games(steam_id) -> SteamLibraryResult`. Knows nothing about the database, IGDB, or FastAPI.
- `app/services/igdb_client.py` — `IgdbClient` class. Manages Twitch OAuth token internally (cache + refresh). Two public methods: `lookup_by_steam_appid(appid) -> int | None` and `get_game(igdb_id) -> IgdbGame | None`.
- `app/services/library_sync.py` — `LibrarySyncService` class. The only orchestrator. Pulls from Steam, looks up in IGDB, writes via repositories, records a `DataSyncRun`. Handles all the partial / failure modes.
- `app/db/repositories.py` — `GameRepository`, `LibraryEntryRepository`, `SyncRunRepository`. The only place SQLAlchemy ORM is touched outside `models.py`. Services receive a repository instance, not a Session.
- `app/api/library.py` — three endpoints, each thin: parse input, call a service / repository, return JSON.

**Boundary contract (this is the resume-grade discipline):** No file in `services/` or `db/repositories.py` imports from `api/`. No file in `services/steam_client.py` or `services/igdb_client.py` imports SQLAlchemy. `library_sync.py` is the only service that touches the repositories.

---

## Task 1: Configuration, `.env.example`, and `respx` dev dep

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Create: `backend/.env.example`
- Create: `backend/.env` (locally only — gitignored)

- [ ] **Step 1: Add `respx` to `backend/pyproject.toml` dev deps**

Open `backend/pyproject.toml`. Replace the `[project.optional-dependencies]` block with:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "ruff>=0.3",
    "mypy>=1.9",
]
```

(Add `"respx>=0.21",` between `pytest-asyncio` and `ruff`. Leave everything else alone.)

- [ ] **Step 2: Reinstall to pick up `respx`**

```bash
cd /c/dev/what-should-i-play/backend
.venv/Scripts/python.exe -m pip install -e ".[dev]" --quiet
.venv/Scripts/python.exe -c "import respx; print('respx', respx.__version__)"
```

Expected: prints `respx 0.21.x` (or higher).

- [ ] **Step 3: Add API-key fields to `backend/app/config.py`**

Replace the entire contents of `backend/app/config.py` with:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "What Should I Play?"
    database_url: str = "sqlite:///./wsip.db"
    cors_origins: list[str] = ["http://localhost:5173"]

    # External APIs (empty defaults so tests can run without keys configured)
    steam_api_key: str = ""
    steam_user_id: str = ""
    igdb_client_id: str = ""
    igdb_client_secret: str = ""

    # HTTP timeouts (seconds)
    http_timeout_seconds: float = 10.0


settings = Settings()
```

- [ ] **Step 4: Create `backend/.env.example`**

```
# Copy this file to .env and fill in your values.
# .env is gitignored; .env.example is committed.

# Steam Web API key (32-char hex).
# Get yours at https://steamcommunity.com/dev/apikey
STEAM_API_KEY=

# Your numeric Steam ID (17 digits, NOT your nickname).
# Find it via https://steamid.io if you don't know it.
STEAM_USER_ID=

# IGDB credentials (issued by Twitch's developer console).
# Create an app at https://dev.twitch.tv/console
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
```

- [ ] **Step 5: Create your local `backend/.env` and fill in the four real values**

```bash
cd /c/dev/what-should-i-play/backend
cp .env.example .env
```

Then open `backend/.env` in any editor and paste your actual Steam API key, Steam ID, IGDB Client ID, and IGDB Client Secret. **Do NOT commit `.env`** — it is already gitignored at the repo root (the rule is `.env`).

- [ ] **Step 6: Verify config loads with the new fields**

```bash
cd /c/dev/what-should-i-play/backend
.venv/Scripts/python.exe -c "from app.config import settings; print('steam_api_key set:', bool(settings.steam_api_key)); print('igdb_client_id set:', bool(settings.igdb_client_id))"
```

Expected: both print `True` (since you filled in `.env`).

- [ ] **Step 7: Verify ruff is clean**

```bash
.venv/Scripts/ruff.exe check .
```

Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
cd /c/dev/what-should-i-play
git add backend/pyproject.toml backend/app/config.py backend/.env.example
git commit -m "feat(backend): add Steam/IGDB config fields and respx dev dep"
```

(`.env` is NOT in this commit — git status should still show it as ignored.)

---

## Task 2: Steam client with respx-mocked tests

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/app/services/__init__.py` (empty)
- Create: `backend/app/services/steam_client.py`
- Create: `backend/tests/test_steam_client.py`

- [ ] **Step 1: Create empty `backend/app/services/__init__.py`**

File has no content.

- [ ] **Step 2: Add a `respx_mock` fixture to `backend/tests/conftest.py`**

Open the existing `conftest.py`. Add the following imports and fixture at the bottom (do NOT remove anything that's already there):

```python
import respx as _respx_module


@pytest.fixture
def respx_mock():
    """Yields a respx router that intercepts all httpx requests during the test."""
    with _respx_module.mock(assert_all_called=False) as router:
        yield router
```

- [ ] **Step 3: Write the failing tests in `backend/tests/test_steam_client.py`**

```python
import httpx
import pytest

from app.services.steam_client import (
    InvalidSteamIdError,
    PrivateProfileError,
    SteamClient,
    SteamRateLimitError,
)


STEAM_BASE = "https://api.steampowered.com"


def test_get_owned_games_returns_parsed_games(respx_mock) -> None:
    respx_mock.get(f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/").respond(
        200,
        json={
            "response": {
                "game_count": 2,
                "games": [
                    {"appid": 220, "name": "Half-Life 2", "playtime_forever": 1200, "img_icon_url": "abc"},
                    {"appid": 367520, "name": "Hollow Knight", "playtime_forever": 4500, "img_icon_url": "def"},
                ],
            }
        },
    )

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    result = client.get_owned_games("76561198000000000")

    assert result.game_count == 2
    assert len(result.games) == 2
    assert result.games[0].appid == 220
    assert result.games[0].name == "Half-Life 2"
    assert result.games[0].playtime_minutes == 1200
    assert result.games[1].appid == 367520


def test_private_profile_raises(respx_mock) -> None:
    # Steam returns a 200 with empty response object when the profile is private.
    respx_mock.get(f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/").respond(
        200, json={"response": {}}
    )

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(PrivateProfileError):
        client.get_owned_games("76561198000000000")


def test_invalid_steam_id_raises(respx_mock) -> None:
    # An invalid/non-numeric steamid yields HTTP 500 from Steam.
    respx_mock.get(f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/").respond(500, text="Internal Server Error")

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(InvalidSteamIdError):
        client.get_owned_games("not_a_real_id")


def test_rate_limit_raises(respx_mock) -> None:
    respx_mock.get(f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/").respond(429, text="Too Many Requests")

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(SteamRateLimitError):
        client.get_owned_games("76561198000000000")


def test_query_includes_required_params(respx_mock) -> None:
    route = respx_mock.get(f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/").respond(
        200, json={"response": {"game_count": 0, "games": []}}
    )

    client = SteamClient(api_key="MY_KEY", timeout_seconds=5.0)
    client.get_owned_games("76561198000000000")

    request = route.calls.last.request
    assert request.url.params["key"] == "MY_KEY"
    assert request.url.params["steamid"] == "76561198000000000"
    assert request.url.params["format"] == "json"
    assert request.url.params["include_appinfo"] == "true"
    assert request.url.params["include_played_free_games"] == "true"


def test_network_error_raises_httpx_error(respx_mock) -> None:
    respx_mock.get(f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/").mock(
        side_effect=httpx.ConnectError("nope")
    )

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(httpx.ConnectError):
        client.get_owned_games("76561198000000000")
```

- [ ] **Step 4: Run the tests to confirm they fail**

```bash
cd /c/dev/what-should-i-play/backend
.venv/Scripts/pytest.exe tests/test_steam_client.py -v
```

Expected: ImportError on `app.services.steam_client` — module not yet created.

- [ ] **Step 5: Create `backend/app/services/steam_client.py`**

```python
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
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url, params=params)

        if response.status_code == 429:
            raise SteamRateLimitError("Steam rate limit hit (HTTP 429).")
        if response.status_code >= 500:
            raise InvalidSteamIdError(
                f"Steam returned {response.status_code} — usually means an invalid steamid."
            )
        response.raise_for_status()

        payload = response.json().get("response", {})
        if "games" not in payload:
            # Steam returns {"response": {}} for private profiles or accounts
            # with no games purchased. We treat both as PrivateProfileError;
            # the orchestrator can refine the message if needed.
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
        return SteamLibraryResult(game_count=int(payload.get("game_count", len(games))), games=games)
```

- [ ] **Step 6: Run the tests to confirm they pass**

```bash
.venv/Scripts/pytest.exe tests/test_steam_client.py -v
```

Expected: 6 passed.

- [ ] **Step 7: Run the full test suite — should be 15 passed (9 existing + 6 new)**

```bash
.venv/Scripts/pytest.exe -v
```

- [ ] **Step 8: Verify ruff clean**

```bash
.venv/Scripts/ruff.exe check .
```

- [ ] **Step 9: Commit**

```bash
cd /c/dev/what-should-i-play
git add backend/app/services/__init__.py backend/app/services/steam_client.py backend/tests/conftest.py backend/tests/test_steam_client.py
git commit -m "feat(backend): add Steam Web API client with private/invalid/429 handling"
```

---

## Task 3: IGDB Twitch OAuth (token cache + refresh)

**Files:**
- Create: `backend/app/services/igdb_client.py` (initial scaffold — auth only; game lookup added in Task 4)
- Create: `backend/tests/test_igdb_client.py` (auth tests only — game lookup tests added in Task 4)

- [ ] **Step 1: Write the failing OAuth tests in `backend/tests/test_igdb_client.py`**

```python
from datetime import datetime, timedelta

import httpx
import pytest

from app.services.igdb_client import IgdbAuth, IgdbAuthError

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def test_fetches_token_on_first_call(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).respond(
        200, json={"access_token": "tok_abc", "expires_in": 5400, "token_type": "bearer"}
    )

    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    token = auth.get_token()

    assert token == "tok_abc"


def test_caches_token_until_expiration(respx_mock) -> None:
    route = respx_mock.post(TWITCH_TOKEN_URL).respond(
        200, json={"access_token": "tok_abc", "expires_in": 5400, "token_type": "bearer"}
    )

    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    auth.get_token()
    auth.get_token()
    auth.get_token()

    assert route.call_count == 1


def test_refetches_after_expiration(respx_mock) -> None:
    route = respx_mock.post(TWITCH_TOKEN_URL).respond(
        200, json={"access_token": "tok_old", "expires_in": 5400, "token_type": "bearer"}
    )
    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    auth.get_token()

    # Force expiration by rewinding the cached expiration manually.
    auth._expires_at = datetime.utcnow() - timedelta(seconds=1)

    route.respond(200, json={"access_token": "tok_new", "expires_in": 5400, "token_type": "bearer"})
    new_token = auth.get_token()
    assert new_token == "tok_new"
    assert route.call_count == 2


def test_bad_credentials_raise(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).respond(
        401, json={"status": 401, "message": "invalid client"}
    )

    auth = IgdbAuth(client_id="bad", client_secret="bad")
    with pytest.raises(IgdbAuthError):
        auth.get_token()


def test_token_request_sends_required_form_fields(respx_mock) -> None:
    route = respx_mock.post(TWITCH_TOKEN_URL).respond(
        200, json={"access_token": "tok", "expires_in": 5400, "token_type": "bearer"}
    )

    auth = IgdbAuth(client_id="my_id", client_secret="my_secret")
    auth.get_token()

    body = route.calls.last.request.content.decode()
    assert "client_id=my_id" in body
    assert "client_secret=my_secret" in body
    assert "grant_type=client_credentials" in body


def test_network_error_propagates(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).mock(side_effect=httpx.ConnectError("nope"))

    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    with pytest.raises(httpx.ConnectError):
        auth.get_token()
```

- [ ] **Step 2: Run to confirm fail**

```bash
.venv/Scripts/pytest.exe tests/test_igdb_client.py -v
```

Expected: ImportError on `app.services.igdb_client`.

- [ ] **Step 3: Create `backend/app/services/igdb_client.py` with the auth class only**

```python
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

    def __init__(self, client_id: str, client_secret: str, timeout_seconds: float = 10.0) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout_seconds
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def get_token(self) -> str:
        if self._token is not None and self._expires_at is not None and datetime.utcnow() < self._expires_at:
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
        self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in - _EXPIRATION_SAFETY_SECONDS)
        return token
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/Scripts/pytest.exe tests/test_igdb_client.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Verify ruff clean and full suite green**

```bash
.venv/Scripts/ruff.exe check .
.venv/Scripts/pytest.exe -v 2>&1 | tail -3
```

Expected: ruff clean, 21 passed (15 + 6).

- [ ] **Step 6: Commit**

```bash
cd /c/dev/what-should-i-play
git add backend/app/services/igdb_client.py backend/tests/test_igdb_client.py
git commit -m "feat(backend): add IGDB Twitch OAuth client with token caching"
```

---

## Task 4: IGDB game lookup (Steam appid → IGDB id → metadata)

**Files:**
- Modify: `backend/app/services/igdb_client.py` (add `IgdbClient` class)
- Modify: `backend/tests/test_igdb_client.py` (add lookup tests)

- [ ] **Step 1: Append game-lookup tests to `backend/tests/test_igdb_client.py`**

Add these tests AFTER the existing tests (do not remove anything):

```python
from app.services.igdb_client import IgdbClient, IgdbGame

IGDB_EXTERNAL = "https://api.igdb.com/v4/external_games"
IGDB_GAMES = "https://api.igdb.com/v4/games"


def _stub_token(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).respond(
        200, json={"access_token": "tok", "expires_in": 5400, "token_type": "bearer"}
    )


def test_lookup_by_steam_appid_returns_igdb_id(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_EXTERNAL).respond(
        200, json=[{"id": 999, "uid": "367520", "category": 1, "game": 12345}]
    )

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    igdb_id = client.lookup_by_steam_appid(367520)
    assert igdb_id == 12345


def test_lookup_by_steam_appid_returns_none_when_not_found(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_EXTERNAL).respond(200, json=[])

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    assert client.lookup_by_steam_appid(99999999) is None


def test_get_game_returns_metadata(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_GAMES).respond(
        200,
        json=[
            {
                "id": 12345,
                "name": "Hollow Knight",
                "slug": "hollow-knight",
                "summary": "A 2D action adventure.",
                "cover": {"image_id": "co1rgi"},
                "genres": [{"name": "Platform"}, {"name": "Adventure"}],
                "themes": [{"name": "Fantasy"}],
                "first_release_date": 1488499200,  # 2017-03-03
                "total_rating": 91.5,
                "total_rating_count": 800,
                "url": "https://www.igdb.com/games/hollow-knight",
            }
        ],
    )

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    game = client.get_game(12345)

    assert isinstance(game, IgdbGame)
    assert game.igdb_id == 12345
    assert game.name == "Hollow Knight"
    assert game.slug == "hollow-knight"
    assert game.summary == "A 2D action adventure."
    assert game.release_year == 2017
    assert game.critic_score == 91.5
    assert game.cover_url == "https://images.igdb.com/igdb/image/upload/t_cover_big/co1rgi.jpg"
    assert "Platform" in game.genres
    assert "Adventure" in game.genres
    assert "Fantasy" in game.themes


def test_get_game_returns_none_when_not_found(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_GAMES).respond(200, json=[])

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    assert client.get_game(0) is None


def test_get_game_handles_missing_optional_fields(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_GAMES).respond(
        200,
        json=[{"id": 1, "name": "Bare Minimum", "slug": "bare-minimum"}],
    )

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    game = client.get_game(1)

    assert game is not None
    assert game.name == "Bare Minimum"
    assert game.summary is None
    assert game.cover_url is None
    assert game.release_year is None
    assert game.critic_score is None
    assert game.genres == []
    assert game.themes == []


def test_request_includes_client_id_and_bearer(respx_mock) -> None:
    _stub_token(respx_mock)
    route = respx_mock.post(IGDB_EXTERNAL).respond(200, json=[])

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    client.lookup_by_steam_appid(220)

    headers = route.calls.last.request.headers
    assert headers["client-id"] == "cid"
    assert headers["authorization"] == "Bearer tok"
```

- [ ] **Step 2: Run to confirm fail**

```bash
.venv/Scripts/pytest.exe tests/test_igdb_client.py -v
```

Expected: ImportError on `IgdbClient` / `IgdbGame`.

- [ ] **Step 3: Replace the entire `backend/app/services/igdb_client.py` with auth + client**

Open the file and replace its entire contents with:

```python
"""IGDB API client. Uses Twitch OAuth client_credentials for auth."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_EXTERNAL_URL = "https://api.igdb.com/v4/external_games"
IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
IGDB_COVER_URL_TEMPLATE = "https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"

# Refresh the token a minute before it actually expires to avoid edge-case 401s.
_EXPIRATION_SAFETY_SECONDS = 60

# IGDB external_games.category 1 == Steam.
_STEAM_CATEGORY = 1


class IgdbAuthError(Exception):
    """Raised when Twitch refuses our credentials or returns an unexpected token response."""


class IgdbAuth:
    """Caches a Twitch OAuth bearer token, refreshing it when it expires."""

    def __init__(self, client_id: str, client_secret: str, timeout_seconds: float = 10.0) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout_seconds
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def get_token(self) -> str:
        if self._token is not None and self._expires_at is not None and datetime.utcnow() < self._expires_at:
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
        self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in - _EXPIRATION_SAFETY_SECONDS)
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
    def __init__(self, auth: IgdbAuth, client_id: str, timeout_seconds: float = 10.0) -> None:
        self._auth = auth
        self._client_id = client_id
        self._timeout = timeout_seconds

    def lookup_by_steam_appid(self, steam_appid: int) -> int | None:
        body = (
            f'fields game,uid,category; '
            f'where category = {_STEAM_CATEGORY} & uid = "{steam_appid}";'
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

        genres = [g["name"] for g in row.get("genres") or [] if isinstance(g, dict) and g.get("name")]
        themes = [t["name"] for t in row.get("themes") or [] if isinstance(t, dict) and t.get("name")]

        return IgdbGame(
            igdb_id=int(row["id"]),
            name=str(row.get("name", "Unknown")),
            slug=str(row.get("slug", "")),
            summary=row.get("summary"),
            cover_url=cover_url,
            release_year=release_year,
            critic_score=float(row["total_rating"]) if row.get("total_rating") is not None else None,
            critic_score_count=int(row["total_rating_count"]) if row.get("total_rating_count") is not None else None,
            genres=genres,
            themes=themes,
            igdb_url=row.get("url"),
        )
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/Scripts/pytest.exe tests/test_igdb_client.py -v
```

Expected: 12 passed (6 auth + 6 game-lookup).

- [ ] **Step 5: Full suite + ruff**

```bash
.venv/Scripts/pytest.exe -v 2>&1 | tail -3
.venv/Scripts/ruff.exe check .
```

Expected: 27 passed (21 + 6 new). Ruff clean.

- [ ] **Step 6: Commit**

```bash
cd /c/dev/what-should-i-play
git add backend/app/services/igdb_client.py backend/tests/test_igdb_client.py
git commit -m "feat(backend): add IGDB game lookup (Steam appid -> IGDB metadata)"
```

---

## Task 5: Repository layer (catalog, library, sync runs)

**Files:**
- Create: `backend/app/db/repositories.py`
- Create: `backend/tests/test_repositories.py`

- [ ] **Step 1: Write failing tests in `backend/tests/test_repositories.py`**

```python
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import DataSyncRun, Game, LibraryEntry
from app.db.repositories import GameRepository, LibraryEntryRepository, SyncRunRepository


# ---------------------------------------------------------------------------
# GameRepository
# ---------------------------------------------------------------------------


def test_upsert_game_creates_when_missing(db_session: Session) -> None:
    repo = GameRepository(db_session)
    game = repo.upsert(
        igdb_id=12345,
        steam_appid=367520,
        name="Hollow Knight",
        slug="hollow-knight",
        summary="An indie classic.",
        cover_url="https://example.com/hk.jpg",
        critic_score=91.5,
        release_year=2017,
    )
    db_session.commit()

    assert game.id is not None
    assert game.igdb_id == 12345
    assert game.steam_appid == 367520
    assert db_session.query(Game).count() == 1


def test_upsert_game_updates_existing_by_igdb_id(db_session: Session) -> None:
    repo = GameRepository(db_session)
    repo.upsert(igdb_id=12345, steam_appid=367520, name="Hollow Knight", slug="hollow-knight")
    db_session.commit()

    repo.upsert(
        igdb_id=12345,
        steam_appid=367520,
        name="Hollow Knight",
        slug="hollow-knight",
        critic_score=92.0,  # updated
    )
    db_session.commit()

    rows = db_session.query(Game).all()
    assert len(rows) == 1
    assert rows[0].critic_score == 92.0


def test_upsert_game_matches_by_steam_appid_when_no_igdb_id(db_session: Session) -> None:
    repo = GameRepository(db_session)
    repo.upsert(igdb_id=None, steam_appid=220, name="Half-Life 2", slug="half-life-2")
    db_session.commit()

    # Second call with same steam_appid but igdb_id later discovered.
    repo.upsert(igdb_id=300, steam_appid=220, name="Half-Life 2", slug="half-life-2")
    db_session.commit()

    rows = db_session.query(Game).all()
    assert len(rows) == 1
    assert rows[0].igdb_id == 300


# ---------------------------------------------------------------------------
# LibraryEntryRepository
# ---------------------------------------------------------------------------


def test_upsert_library_entry_creates_when_missing(db_session: Session) -> None:
    repo_g = GameRepository(db_session)
    g = repo_g.upsert(igdb_id=1, steam_appid=10, name="X", slug="x")
    db_session.commit()

    repo = LibraryEntryRepository(db_session)
    repo.upsert(game_id=g.id, source="steam", external_id="10", hours_played=12.5)
    db_session.commit()

    rows = db_session.query(LibraryEntry).all()
    assert len(rows) == 1
    assert rows[0].hours_played == 12.5


def test_upsert_library_entry_updates_hours(db_session: Session) -> None:
    repo_g = GameRepository(db_session)
    g = repo_g.upsert(igdb_id=1, steam_appid=10, name="X", slug="x")
    db_session.commit()

    repo = LibraryEntryRepository(db_session)
    repo.upsert(game_id=g.id, source="steam", external_id="10", hours_played=10.0)
    db_session.commit()
    repo.upsert(game_id=g.id, source="steam", external_id="10", hours_played=42.0)
    db_session.commit()

    row = db_session.query(LibraryEntry).one()
    assert row.hours_played == 42.0


def test_list_all_returns_games_with_library_entries(db_session: Session) -> None:
    g_repo = GameRepository(db_session)
    g1 = g_repo.upsert(igdb_id=1, steam_appid=10, name="In Library", slug="in-library")
    g2 = g_repo.upsert(igdb_id=2, steam_appid=20, name="Not In Library", slug="not-in-library")
    db_session.commit()

    LibraryEntryRepository(db_session).upsert(
        game_id=g1.id, source="steam", external_id="10", hours_played=1.0
    )
    db_session.commit()

    rows = LibraryEntryRepository(db_session).list_all_with_games()
    assert len(rows) == 1
    entry, game = rows[0]
    assert entry.game_id == g1.id
    assert game.name == "In Library"
    # g2 should not appear because it has no library entry.
    assert all(g.id != g2.id for _, g in rows)


# ---------------------------------------------------------------------------
# SyncRunRepository
# ---------------------------------------------------------------------------


def test_start_run_creates_in_progress_row(db_session: Session) -> None:
    repo = SyncRunRepository(db_session)
    run = repo.start("steam")
    db_session.commit()

    assert run.id is not None
    assert run.source == "steam"
    assert run.status == "ok"  # placeholder until finish()
    assert run.finished_at is None


def test_finish_run_records_status_and_counts(db_session: Session) -> None:
    repo = SyncRunRepository(db_session)
    run = repo.start("steam")
    db_session.commit()

    repo.finish(run, status="ok", counts={"added": 10, "updated": 2}, error=None)
    db_session.commit()

    fresh = db_session.query(DataSyncRun).filter_by(id=run.id).one()
    assert fresh.status == "ok"
    assert fresh.counts == {"added": 10, "updated": 2}
    assert fresh.finished_at is not None
    assert fresh.error is None


def test_finish_run_records_failure(db_session: Session) -> None:
    repo = SyncRunRepository(db_session)
    run = repo.start("steam")
    db_session.commit()

    repo.finish(run, status="failed", counts={}, error="profile is private")
    db_session.commit()

    fresh = db_session.query(DataSyncRun).filter_by(id=run.id).one()
    assert fresh.status == "failed"
    assert fresh.error == "profile is private"


def test_list_recent_returns_descending_by_started_at(db_session: Session) -> None:
    repo = SyncRunRepository(db_session)
    a = repo.start("steam")
    db_session.commit()
    b = repo.start("igdb")
    db_session.commit()

    # Force ordering by adjusting started_at directly so the test is deterministic.
    a.started_at = datetime(2026, 1, 1)
    b.started_at = datetime(2026, 5, 1)
    db_session.commit()

    rows = repo.list_recent(limit=10)
    assert [r.id for r in rows] == [b.id, a.id]
```

- [ ] **Step 2: Run to confirm fail**

```bash
.venv/Scripts/pytest.exe tests/test_repositories.py -v
```

Expected: ImportError on `app.db.repositories`.

- [ ] **Step 3: Create `backend/app/db/repositories.py`**

```python
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
            existing = self._session.scalar(select(Game).where(Game.steam_appid == steam_appid))

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
            existing = LibraryEntry(game_id=game_id, source=source, hours_played=hours_played)
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
```

- [ ] **Step 4: Run tests, full suite, ruff**

```bash
.venv/Scripts/pytest.exe tests/test_repositories.py -v
.venv/Scripts/pytest.exe -v 2>&1 | tail -3
.venv/Scripts/ruff.exe check .
```

Expected: 10 repo tests pass, 37 total (27 + 10), ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/what-should-i-play
git add backend/app/db/repositories.py backend/tests/test_repositories.py
git commit -m "feat(backend): add repositories for games, library entries, sync runs"
```

---

## Task 6: Library sync orchestrator

**Files:**
- Create: `backend/app/services/library_sync.py`
- Create: `backend/tests/test_library_sync.py`

This is the keystone of the sub-plan: the only place that knows about Steam, IGDB, and the database all at once.

- [ ] **Step 1: Write failing tests in `backend/tests/test_library_sync.py`**

```python
from typing import Optional

import pytest
from sqlalchemy.orm import Session

from app.db.models import DataSyncRun, Game, LibraryEntry
from app.db.repositories import GameRepository, LibraryEntryRepository, SyncRunRepository
from app.services.igdb_client import IgdbGame
from app.services.library_sync import LibrarySyncService, SyncOutcome
from app.services.steam_client import (
    PrivateProfileError,
    SteamGame,
    SteamLibraryResult,
    SteamRateLimitError,
)


# --- Test doubles --------------------------------------------------------


class FakeSteamClient:
    def __init__(self, result=None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc

    def get_owned_games(self, steam_id: str) -> SteamLibraryResult:
        if self._exc is not None:
            raise self._exc
        return self._result


class FakeIgdbClient:
    """Maps Steam appid -> (igdb_id, IgdbGame). None igdb_id => not found."""

    def __init__(self, mapping: dict[int, tuple[int | None, IgdbGame | None]]) -> None:
        self._mapping = mapping

    def lookup_by_steam_appid(self, steam_appid: int) -> Optional[int]:
        return self._mapping.get(steam_appid, (None, None))[0]

    def get_game(self, igdb_id: int) -> Optional[IgdbGame]:
        for _, (mapped_id, igdb_game) in self._mapping.items():
            if mapped_id == igdb_id:
                return igdb_game
        return None


def _make_service(
    db_session: Session,
    steam: FakeSteamClient,
    igdb: FakeIgdbClient,
) -> LibrarySyncService:
    return LibrarySyncService(
        steam_client=steam,
        igdb_client=igdb,
        games=GameRepository(db_session),
        library=LibraryEntryRepository(db_session),
        sync_runs=SyncRunRepository(db_session),
        session=db_session,
    )


# --- Tests ---------------------------------------------------------------


def test_successful_sync_creates_games_library_and_run(db_session: Session) -> None:
    steam = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=2,
            games=[
                SteamGame(appid=220, name="Half-Life 2", playtime_minutes=600, icon_hash="a"),
                SteamGame(appid=367520, name="Hollow Knight", playtime_minutes=4500, icon_hash="b"),
            ],
        )
    )
    igdb = FakeIgdbClient(
        {
            220: (
                100,
                IgdbGame(igdb_id=100, name="Half-Life 2", slug="half-life-2", critic_score=96.0),
            ),
            367520: (
                200,
                IgdbGame(
                    igdb_id=200,
                    name="Hollow Knight",
                    slug="hollow-knight",
                    critic_score=91.5,
                    release_year=2017,
                ),
            ),
        }
    )

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "ok"
    assert outcome.counts["added"] == 2
    assert outcome.counts["updated"] == 0
    assert outcome.error is None

    assert db_session.query(Game).count() == 2
    assert db_session.query(LibraryEntry).count() == 2

    runs = db_session.query(DataSyncRun).all()
    assert len(runs) == 1
    assert runs[0].status == "ok"
    assert runs[0].finished_at is not None


def test_private_profile_marks_run_failed_with_no_writes(db_session: Session) -> None:
    steam = FakeSteamClient(exc=PrivateProfileError("profile is private"))
    igdb = FakeIgdbClient({})

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "failed"
    assert "private" in outcome.error.lower()
    assert db_session.query(Game).count() == 0
    assert db_session.query(LibraryEntry).count() == 0

    run = db_session.query(DataSyncRun).one()
    assert run.status == "failed"
    assert "private" in (run.error or "").lower()


def test_rate_limit_marks_run_failed(db_session: Session) -> None:
    steam = FakeSteamClient(exc=SteamRateLimitError("429"))
    igdb = FakeIgdbClient({})

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "failed"
    assert "rate" in outcome.error.lower()


def test_partial_when_some_igdb_lookups_fail(db_session: Session) -> None:
    steam = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=2,
            games=[
                SteamGame(appid=220, name="Half-Life 2", playtime_minutes=600, icon_hash="a"),
                SteamGame(appid=999999, name="Obscure Indie", playtime_minutes=10, icon_hash="z"),
            ],
        )
    )
    # Only 220 is found; 999999 has no IGDB mapping.
    igdb = FakeIgdbClient(
        {
            220: (100, IgdbGame(igdb_id=100, name="Half-Life 2", slug="half-life-2")),
            999999: (None, None),
        }
    )

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "partial"
    assert outcome.counts["added"] == 2  # both games added — Steam is the source of truth
    assert outcome.counts["unmatched_igdb"] == 1
    # The matched game has IGDB metadata; the unmatched one is added with steam-only fields.
    matched = (
        db_session.query(Game).filter(Game.steam_appid == 220).one()
    )
    assert matched.igdb_id == 100
    unmatched = (
        db_session.query(Game).filter(Game.steam_appid == 999999).one()
    )
    assert unmatched.igdb_id is None
    assert unmatched.name == "Obscure Indie"


def test_rerun_updates_existing_library_entries(db_session: Session) -> None:
    steam_first = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=1,
            games=[SteamGame(appid=220, name="Half-Life 2", playtime_minutes=600, icon_hash="a")],
        )
    )
    igdb = FakeIgdbClient(
        {220: (100, IgdbGame(igdb_id=100, name="Half-Life 2", slug="half-life-2"))}
    )

    _make_service(db_session, steam_first, igdb).sync_steam(steam_id="x")

    # Second run with updated playtime.
    steam_second = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=1,
            games=[SteamGame(appid=220, name="Half-Life 2", playtime_minutes=1200, icon_hash="a")],
        )
    )
    outcome = _make_service(db_session, steam_second, igdb).sync_steam(steam_id="x")

    assert outcome.counts["added"] == 0
    assert outcome.counts["updated"] == 1

    entry = db_session.query(LibraryEntry).one()
    # 1200 minutes -> 20.0 hours
    assert entry.hours_played == pytest.approx(20.0)


def test_outcome_is_a_dataclass_with_expected_fields(db_session: Session) -> None:
    steam = FakeSteamClient(result=SteamLibraryResult(game_count=0, games=[]))
    igdb = FakeIgdbClient({})
    outcome = _make_service(db_session, steam, igdb).sync_steam(steam_id="x")

    assert isinstance(outcome, SyncOutcome)
    assert outcome.run_id > 0
    assert outcome.status in {"ok", "partial", "failed"}
    assert isinstance(outcome.counts, dict)
```

- [ ] **Step 2: Run to confirm fail**

```bash
.venv/Scripts/pytest.exe tests/test_library_sync.py -v
```

Expected: ImportError on `app.services.library_sync`.

- [ ] **Step 3: Create `backend/app/services/library_sync.py`**

```python
"""Orchestrates a Steam library import: Steam -> IGDB -> repositories.

This is the only service that knows about all three. Steam and IGDB clients
remain ignorant of each other and of the database.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.repositories import GameRepository, LibraryEntryRepository, SyncRunRepository
from app.services.igdb_client import IgdbClient, IgdbGame
from app.services.steam_client import (
    PrivateProfileError,
    SteamClient,
    SteamClientError,
    SteamGame,
)


@dataclass(frozen=True)
class SyncOutcome:
    run_id: int
    status: str  # "ok" | "partial" | "failed"
    counts: dict = field(default_factory=dict)
    error: str | None = None


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
        except PrivateProfileError as e:
            self._runs.finish(run, status="failed", counts={}, error=str(e))
            self._session.commit()
            return SyncOutcome(run_id=run.id, status="failed", counts={}, error=str(e))
        except SteamClientError as e:
            self._runs.finish(run, status="failed", counts={}, error=str(e))
            self._session.commit()
            return SyncOutcome(run_id=run.id, status="failed", counts={}, error=str(e))

        # Snapshot existing library so we can classify each game as added vs updated
        # in O(1) — avoids an O(n^2) scan inside the loop for large libraries.
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
            slug=igdb_game.slug or _slugify_steam(steam_game.appid, steam_game.name),
            summary=igdb_game.summary,
            cover_url=igdb_game.cover_url,
            store_url=f"https://store.steampowered.com/app/{steam_game.appid}/",
            critic_score=igdb_game.critic_score,
            release_year=igdb_game.release_year,
        )
```

- [ ] **Step 4: Run tests, full suite, ruff**

```bash
.venv/Scripts/pytest.exe tests/test_library_sync.py -v
.venv/Scripts/pytest.exe -v 2>&1 | tail -3
.venv/Scripts/ruff.exe check .
```

Expected: 6 sync tests pass, 43 total (37 + 6), ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/what-should-i-play
git add backend/app/services/library_sync.py backend/tests/test_library_sync.py
git commit -m "feat(backend): add library sync service (Steam -> IGDB -> DB)"
```

---

## Task 7: HTTP API endpoints (sync trigger + library + sync runs)

**Files:**
- Create: `backend/app/api/library.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_library_api.py`

- [ ] **Step 1: Write failing API tests in `backend/tests/test_library_api.py`**

```python
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import library as library_api
from app.db.models import DataSyncRun, Game, LibraryEntry
from app.db.repositories import GameRepository, LibraryEntryRepository, SyncRunRepository
from app.main import create_app
from app.services.library_sync import SyncOutcome


def _make_client_with_session(db_session: Session) -> TestClient:
    """Builds a TestClient with the DB dependency overridden to use db_session."""
    app = create_app()

    def _override_session():
        yield db_session

    app.dependency_overrides[library_api.get_db_session] = _override_session
    return TestClient(app)


def test_get_library_returns_owned_games(db_session: Session) -> None:
    g = GameRepository(db_session).upsert(
        igdb_id=1, steam_appid=10, name="Half-Life 2", slug="half-life-2", critic_score=96.0
    )
    db_session.commit()
    LibraryEntryRepository(db_session).upsert(
        game_id=g.id, source="steam", external_id="10", hours_played=12.5
    )
    db_session.commit()

    client = _make_client_with_session(db_session)
    res = client.get("/api/library")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    item = body[0]
    assert item["name"] == "Half-Life 2"
    assert item["steam_appid"] == 10
    assert item["hours_played"] == 12.5
    assert item["critic_score"] == 96.0


def test_get_sync_runs_returns_recent_descending(db_session: Session) -> None:
    repo = SyncRunRepository(db_session)
    a = repo.start("steam")
    db_session.commit()
    repo.finish(a, status="ok", counts={"added": 5}, error=None)
    db_session.commit()

    client = _make_client_with_session(db_session)
    res = client.get("/api/library/sync-runs")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["source"] == "steam"
    assert body[0]["status"] == "ok"
    assert body[0]["counts"] == {"added": 5}


def test_post_sync_steam_invokes_service_and_returns_outcome(
    db_session: Session, monkeypatch
) -> None:
    fake_outcome = SyncOutcome(
        run_id=42, status="ok", counts={"added": 7, "updated": 0, "unmatched_igdb": 0}
    )

    captured = {}

    class FakeService:
        def __init__(self, **_kwargs) -> None:
            pass

        def sync_steam(self, *, steam_id: str) -> SyncOutcome:
            captured["steam_id"] = steam_id
            return fake_outcome

    monkeypatch.setattr(library_api, "_build_sync_service", lambda session: FakeService())

    client = _make_client_with_session(db_session)
    res = client.post("/api/library/sync/steam", json={"steam_id": "76561198000000000"})
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "run_id": 42,
        "status": "ok",
        "counts": {"added": 7, "updated": 0, "unmatched_igdb": 0},
        "error": None,
    }
    assert captured["steam_id"] == "76561198000000000"


def test_post_sync_steam_uses_settings_steam_id_when_omitted(
    db_session: Session, monkeypatch
) -> None:
    captured = {}

    class FakeService:
        def __init__(self, **_kwargs) -> None:
            pass

        def sync_steam(self, *, steam_id: str) -> SyncOutcome:
            captured["steam_id"] = steam_id
            return SyncOutcome(run_id=1, status="ok", counts={})

    monkeypatch.setattr(library_api, "_build_sync_service", lambda session: FakeService())
    monkeypatch.setattr(library_api.settings, "steam_user_id", "76561198999999999")

    client = _make_client_with_session(db_session)
    res = client.post("/api/library/sync/steam", json={})
    assert res.status_code == 200
    assert captured["steam_id"] == "76561198999999999"


def test_post_sync_steam_returns_400_when_no_id_anywhere(
    db_session: Session, monkeypatch
) -> None:
    monkeypatch.setattr(library_api.settings, "steam_user_id", "")
    client = _make_client_with_session(db_session)
    res = client.post("/api/library/sync/steam", json={})
    assert res.status_code == 400
    assert "steam id" in res.json()["detail"].lower()
```

- [ ] **Step 2: Run to confirm fail**

```bash
.venv/Scripts/pytest.exe tests/test_library_api.py -v
```

Expected: ImportError on `app.api.library`.

- [ ] **Step 3: Create `backend/app/api/library.py`**

```python
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
from app.db.repositories import GameRepository, LibraryEntryRepository, SyncRunRepository
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
def list_library(session: Session = Depends(get_db_session)) -> list[LibraryItem]:
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
    )


# ---------------------------------------------------------------------------
# Service factory — broken out so tests can monkeypatch it.
# ---------------------------------------------------------------------------


def _build_sync_service(session: Session) -> LibrarySyncService:
    steam = SteamClient(api_key=settings.steam_api_key, timeout_seconds=settings.http_timeout_seconds)
    igdb_auth = IgdbAuth(
        client_id=settings.igdb_client_id,
        client_secret=settings.igdb_client_secret,
        timeout_seconds=settings.http_timeout_seconds,
    )
    igdb = IgdbClient(igdb_auth, client_id=settings.igdb_client_id, timeout_seconds=settings.http_timeout_seconds)
    return LibrarySyncService(
        steam_client=steam,
        igdb_client=igdb,
        games=GameRepository(session),
        library=LibraryEntryRepository(session),
        sync_runs=SyncRunRepository(session),
        session=session,
    )
```

- [ ] **Step 4: Wire the router into `backend/app/main.py`**

Open the file. It currently imports and includes `health.router`. Add the library router right next to it. The full updated file:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, library
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(library.router)
    return app


app = create_app()
```

- [ ] **Step 5: Run the API tests, then full suite, then ruff**

```bash
.venv/Scripts/pytest.exe tests/test_library_api.py -v
.venv/Scripts/pytest.exe -v 2>&1 | tail -5
.venv/Scripts/ruff.exe check .
```

Expected: 5 API tests pass, 48 total, ruff clean.

- [ ] **Step 6: Commit**

```bash
cd /c/dev/what-should-i-play
git add backend/app/api/library.py backend/app/main.py backend/tests/test_library_api.py
git commit -m "feat(backend): add /api/library, /api/library/sync-runs, POST /api/library/sync/steam"
```

---

## Task 8: Real-data smoke test (manual, with your actual API keys)

This task validates the entire pipeline against real Steam + real IGDB. It is the only place in the sub-plan where live API calls happen. No new code; this is verification only.

**Prerequisites:** Tasks 1–7 done; `backend/.env` filled with your real keys; `wsip.db` exists from Alembic.

- [ ] **Step 1: Start the backend**

In one PowerShell:

```powershell
cd C:\dev\what-should-i-play\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Wait for `Application startup complete.`

- [ ] **Step 2: Trigger a Steam sync**

In a second PowerShell, using `curl.exe` (Windows ships this; the unprefixed `curl` is a PowerShell alias that won't accept the same flags):

```powershell
curl.exe -X POST http://localhost:8000/api/library/sync/steam -H "Content-Type: application/json" -d "{}"
```

Expected JSON response (your numbers will vary):

```json
{"run_id": 1, "status": "ok", "counts": {"added": 137, "updated": 0, "unmatched_igdb": 4}, "error": null}
```

`status` will be `"partial"` if any IGDB lookups failed (very common for niche/old games — fine).

`status` will be `"failed"` with `error: "...private..."` if your Steam profile is set to private. Fix: open Steam Profile → Edit Profile → Privacy Settings → Game Details = Public, then re-run.

- [ ] **Step 3: Inspect the sync run**

```powershell
curl.exe http://localhost:8000/api/library/sync-runs
```

Expected: an array with one object showing `source: "steam"`, your `status`, the `counts`, and `started_at` / `finished_at` timestamps.

- [ ] **Step 4: Inspect your imported library**

```powershell
curl.exe http://localhost:8000/api/library
```

Expected: an array of objects, one per owned Steam game, each with `name`, `steam_appid`, `hours_played`, plus `cover_url` / `critic_score` for the games IGDB matched.

- [ ] **Step 5: Sanity-check the database directly**

In a third terminal (or use sqlite3 if you have it; otherwise Python):

```powershell
cd C:\dev\what-should-i-play\backend
.\.venv\Scripts\python.exe -c "import sqlite3; con=sqlite3.connect('wsip.db'); print('games:', con.execute('SELECT COUNT(*) FROM games').fetchone()[0]); print('library:', con.execute('SELECT COUNT(*) FROM library_entries').fetchone()[0]); print('with_igdb:', con.execute('SELECT COUNT(*) FROM games WHERE igdb_id IS NOT NULL').fetchone()[0])"
```

Expected: `games` and `library` should match the `added` count from Step 2; `with_igdb` should equal `added - unmatched_igdb`.

- [ ] **Step 6: Re-run the sync and verify it updates rather than duplicates**

```powershell
curl.exe -X POST http://localhost:8000/api/library/sync/steam -H "Content-Type: application/json" -d "{}"
```

Expected: `counts.added` is `0`, `counts.updated` equals your library size, no duplicate rows in DB. Verify with the same Python one-liner from Step 5 — counts should be identical.

- [ ] **Step 7: Stop the backend (Ctrl+C in its terminal). No commit — this task added no files.**

---

## Task 9: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read the current README**

```bash
cat /c/dev/what-should-i-play/README.md | head -20
```

- [ ] **Step 2: Add an "API Keys" section between the existing "Setup" and "Daily commands" sections**

Open `README.md`. Find the line that starts with `## Daily commands`. Insert this BEFORE it:

```markdown
## API Keys (required for library import)

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Where to get it | Notes |
|---|---|---|
| `STEAM_API_KEY` | https://steamcommunity.com/dev/apikey | Use `localhost` for the domain field. |
| `STEAM_USER_ID` | Your numeric Steam ID (17 digits). Find via https://steamid.io if needed. | NOT your nickname. |
| `IGDB_CLIENT_ID` | https://dev.twitch.tv/console — register an app, "Confidential" client type. | |
| `IGDB_CLIENT_SECRET` | Same Twitch app — click "New Secret". | Treat like a password. |

`backend/.env` is gitignored. Do not commit it.

Triggering an import once keys are set:

```bash
npm run dev
# in another terminal:
curl.exe -X POST http://localhost:8000/api/library/sync/steam -H "Content-Type: application/json" -d "{}"
```

```

- [ ] **Step 3: Update the "Status" section to reflect Sub-plan 2a complete**

Find the existing "## Status" section (a single paragraph). Replace its body with:

```markdown
Foundation + library-import backend complete. Schema spine in place, Steam library imports via `/api/library/sync/steam`, results visible at `/api/library` and `/api/library/sync-runs`. Frontend is still the foundation health-check page; library/onboarding UI ships in Sub-plan 2b.
```

- [ ] **Step 4: Commit**

```bash
cd /c/dev/what-should-i-play
git add README.md
git commit -m "docs: document Steam+IGDB API keys and library sync endpoint"
```

---

## Acceptance Criteria

When this sub-plan is complete, all of the following must hold:

- `npm run test` passes 48+ tests (was 9 after foundation).
- `npm run lint` produces no output.
- `npm run build` is clean (frontend untouched).
- A real `POST /api/library/sync/steam` against your actual Steam ID populates `games` and `library_entries` tables and writes a `data_sync_runs` row.
- Re-running the sync updates rows rather than duplicating them.
- A Steam profile set to private is reported via `status: "failed"` with `"private"` in the error message, and writes nothing to `games` / `library_entries`.
- `git log --oneline` shows ~9 commits since the start of this sub-plan, each scoped to one task.
- `git status` is clean and `backend/.env` does not appear in `git ls-files`.
- CI on GitHub stays green.

---

## What this sub-plan does NOT do

Strict scope guardrails — these belong to later sub-plans:

- Frontend UI (onboarding wizard, library page, rating side panel, status badges) — Sub-plan 2b
- Manual game add via FTS5 search over IGDB — Sub-plan 2b (uses IGDB client built here)
- Rating capture, `Loved/Liked/Meh/Disliked/Hated` UI — Sub-plan 2b
- Background-job framework (we run sync synchronously inside the request for v1; FastAPI BackgroundTasks integration comes later if sync becomes too slow)
- Steam playtime delta capture / `play_sessions` writes — Sub-plan 7
- Recommendations, `recommendation_events` writes, telemetry — Sub-plan 3
- Embeddings, ML, eval harness — Sub-plans 4 and 7
- Steam OAuth (we use API key + manual Steam ID entry, which is fine for single-user local)
- Retry/backoff on rate limits (we surface `429` cleanly and let the user retry)

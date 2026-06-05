# Onboarding, First-Run & Steam-Failure UX Implementation Plan (Sub-plan 2c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 3-step first-run onboarding wizard (Welcome → Connect Steam → Preferences) with first-run detection via a persisted flag, machine-readable Steam error codes, and a full failure taxonomy — making this the first UI that can trigger a Steam sync.

**Architecture:** Backend gains a `SteamAuthError`, a public-empty-library success path, an `error_code` on the sync outcome, an `onboarding_completed` column on the `Preferences` singleton, and a thin `GET/PUT /api/onboarding` router. Frontend adds an `OnboardingGuard` (loop-safe redirect), an `/onboarding` wizard, a pure `onboardingMessages` mapping, a shared `PreferencesForm` (extracted from the 2b page), and a first-time empty state on the Library page.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pytest, respx. Frontend — React 18, Vite, TypeScript (strict), Tailwind v3, shadcn/ui, react-router-dom, Vitest.

**Spec:** `docs/superpowers/specs/2026-05-29-onboarding-design.md`

**Environment notes for the implementer:**
- Repo root: `C:\dev\what-should-i-play\` (Git Bash: `/c/dev/what-should-i-play/`). The bash CWD resets between calls — always prefix with the real path.
- Backend Python via venv: from `backend/`, `.venv/Scripts/python.exe -m pytest` / `... -m ruff check .`. ruff line-length 100, B008 ignored.
- Frontend: from `frontend/`, `npm run build` / `npm run test`. `@/` → `src/`.
- Prefer ASCII in UI strings (Windows mojibake risk); avoid Unicode glyphs unless essential.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

**Backend**
- Modify `app/services/steam_client.py` — `SteamAuthError`; 401/403 handling; public-empty-library success; narrow network/HTTP wrapping.
- Modify `app/services/library_sync.py` — `SyncOutcome.error_code` + exception→code mapping.
- Modify `app/api/library.py` — `SyncOutcomeOut.error_code`.
- Modify `app/db/models.py` — `Preferences.onboarding_completed`.
- Modify `app/db/repositories.py` — `PreferencesRepository.get/set_onboarding_completed`.
- Create `app/api/onboarding.py`; modify `app/main.py`.
- Create `alembic/versions/0002_onboarding.py`.
- Tests: extend `test_steam_client.py`, `test_library_sync.py`, `test_library_api.py`, `test_repositories.py`; new `test_onboarding_api.py`.

**Frontend**
- Modify `src/lib/api.ts` — onboarding + sync types/functions.
- Create `src/lib/onboardingMessages.ts` + `src/lib/onboardingMessages.test.ts`.
- Create `src/components/PreferencesForm.tsx`; modify `src/pages/PreferencesPage.tsx`.
- Create `src/components/OnboardingGuard.tsx`; modify `src/App.tsx`.
- Create `src/pages/OnboardingWizard.tsx`, `src/components/onboarding/WelcomeStep.tsx`, `ConnectStep.tsx`, `PreferencesStep.tsx`.
- Modify `src/pages/LibraryPage.tsx` — first-time empty state.

---

## Task 1: Steam client — auth error, empty-library success, network wrapping

**Files:**
- Modify: `backend/app/services/steam_client.py`
- Test: `backend/tests/test_steam_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_steam_client.py` (and note Step 3 also MODIFIES one existing test):

```python
def test_auth_error_on_401(respx_mock) -> None:
    from app.services.steam_client import SteamAuthError

    respx_mock.get(OWNED_GAMES_PATH).respond(401, text="Unauthorized")
    client = SteamClient(api_key="bad", timeout_seconds=5.0)
    with pytest.raises(SteamAuthError):
        client.get_owned_games("76561198000000000")


def test_auth_error_on_403(respx_mock) -> None:
    from app.services.steam_client import SteamAuthError

    respx_mock.get(OWNED_GAMES_PATH).respond(403, text="Forbidden")
    client = SteamClient(api_key="bad", timeout_seconds=5.0)
    with pytest.raises(SteamAuthError):
        client.get_owned_games("76561198000000000")


def test_public_empty_library_is_success_not_private(respx_mock) -> None:
    # Public profile that owns zero games: response has game_count but no games key.
    respx_mock.get(OWNED_GAMES_PATH).respond(200, json={"response": {"game_count": 0}})
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    result = client.get_owned_games("76561198000000000")
    assert result.game_count == 0
    assert result.games == []


def test_truly_empty_response_still_private(respx_mock) -> None:
    respx_mock.get(OWNED_GAMES_PATH).respond(200, json={"response": {}})
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(PrivateProfileError):
        client.get_owned_games("76561198000000000")


def test_network_error_wrapped_as_steam_error(respx_mock) -> None:
    from app.services.steam_client import SteamClientError

    respx_mock.get(OWNED_GAMES_PATH).mock(side_effect=httpx.ConnectError("nope"))
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(SteamClientError):
        client.get_owned_games("76561198000000000")


def test_parse_error_is_not_swallowed(respx_mock) -> None:
    # A games entry missing 'appid' is a contract bug, not a Steam failure:
    # it must surface as KeyError, NOT be wrapped into SteamClientError.
    respx_mock.get(OWNED_GAMES_PATH).respond(
        200, json={"response": {"game_count": 1, "games": [{"name": "no appid"}]}}
    )
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(KeyError):
        client.get_owned_games("76561198000000000")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_steam_client.py -k "auth_error or empty_library or truly_empty or network_error_wrapped or parse_error" -v`
Expected: FAIL (`SteamAuthError` import error; empty-library raises `PrivateProfileError`; network raises bare `httpx.ConnectError`).

- [ ] **Step 3: Update the now-obsolete network test**

In `backend/tests/test_steam_client.py`, the existing `test_network_error_raises_httpx_error` asserts a bare `httpx.ConnectError` propagates. Wrapping changes that. DELETE that old test (the new `test_network_error_wrapped_as_steam_error` replaces it). Remove this block:

```python
def test_network_error_raises_httpx_error(respx_mock) -> None:
    respx_mock.get(OWNED_GAMES_PATH).mock(side_effect=httpx.ConnectError("nope"))

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(httpx.ConnectError):
        client.get_owned_games("76561198000000000")
```

- [ ] **Step 4: Implement the steam_client changes**

In `backend/app/services/steam_client.py`, add the new error class after `SteamRateLimitError`:

```python
class SteamAuthError(SteamClientError):
    """Steam returned 401/403 — the API key is missing or invalid."""
```

Replace the body of `get_owned_games` (from the `with httpx.Client...` block through the `return`) with:

```python
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
```

- [ ] **Step 5: Run the full steam_client suite**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_steam_client.py -v`
Expected: PASS (all, including the unchanged 429/5xx/private/params tests).

- [ ] **Step 6: Lint + commit**

```bash
cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m ruff check .
```

```bash
cd /c/dev/what-should-i-play && git add backend/app/services/steam_client.py backend/tests/test_steam_client.py
git commit -m "feat: SteamAuthError, public-empty-library success, network wrapping"
```

---

## Task 2: Sync orchestration — error_code mapping

**Files:**
- Modify: `backend/app/services/library_sync.py`
- Test: `backend/tests/test_library_sync.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_library_sync.py`. First extend the import at the top of the file to add the error types:

```python
from app.services.steam_client import (
    InvalidSteamIdError,
    PrivateProfileError,
    SteamAuthError,
    SteamClientError,
    SteamGame,
    SteamLibraryResult,
    SteamRateLimitError,
)
```

Then add the tests:

```python
@pytest.mark.parametrize(
    "exc, expected_code",
    [
        (PrivateProfileError("x"), "private_profile"),
        (SteamAuthError("x"), "steam_auth"),
        (SteamRateLimitError("x"), "rate_limited"),
        (InvalidSteamIdError("x"), "invalid_steamid"),
        (SteamClientError("x"), "steam_error"),
    ],
)
def test_sync_maps_exception_to_error_code(db_session, exc, expected_code) -> None:
    steam = FakeSteamClient(exc=exc)
    igdb = FakeIgdbClient({})
    service = _make_service(db_session, steam, igdb)

    outcome = service.sync_steam(steam_id="76561198000000000")
    assert outcome.status == "failed"
    assert outcome.error_code == expected_code


def test_sync_zero_games_is_ok_with_no_error_code(db_session) -> None:
    steam = FakeSteamClient(result=SteamLibraryResult(game_count=0, games=[]))
    igdb = FakeIgdbClient({})
    service = _make_service(db_session, steam, igdb)

    outcome = service.sync_steam(steam_id="76561198000000000")
    assert outcome.status == "ok"
    assert outcome.error_code is None
    assert outcome.counts == {"added": 0, "updated": 0, "unmatched_igdb": 0}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_library_sync.py -k "error_code or zero_games" -v`
Expected: FAIL (`SyncOutcome` has no `error_code`).

- [ ] **Step 3: Implement the mapping**

In `backend/app/services/library_sync.py`:

Extend the steam_client import to include the new types:

```python
from app.services.steam_client import (
    InvalidSteamIdError,
    PrivateProfileError,
    SteamAuthError,
    SteamClient,
    SteamClientError,
    SteamGame,
    SteamRateLimitError,
)
```

Add `error_code` to the dataclass:

```python
@dataclass(frozen=True)
class SyncOutcome:
    run_id: int
    status: str  # "ok" | "partial" | "failed"
    counts: dict = field(default_factory=dict)
    error: str | None = None
    error_code: str | None = None
```

Add a module-level mapping helper (after the dataclass):

```python
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
```

Replace the two `except` blocks in `sync_steam` (the `PrivateProfileError` and `SteamClientError` handlers) with a single handler — `PrivateProfileError` is a `SteamClientError` subclass so one catch covers all:

```python
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
```

(The success path keeps `error_code` at its default `None`.)

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_library_sync.py -v`
Expected: PASS (all, including pre-existing sync tests).

- [ ] **Step 5: Lint + commit**

```bash
cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m ruff check .
```

```bash
cd /c/dev/what-should-i-play && git add backend/app/services/library_sync.py backend/tests/test_library_sync.py
git commit -m "feat: map Steam exceptions to stable error_code on SyncOutcome"
```

---

## Task 3: Library API — expose error_code

**Files:**
- Modify: `backend/app/api/library.py`
- Test: `backend/tests/test_library_api.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_library_api.py`:

```python
def test_sync_steam_returns_error_code(db_session: Session, monkeypatch) -> None:
    fake_outcome = SyncOutcome(
        run_id=9,
        status="failed",
        counts={},
        error="profile is private",
        error_code="private_profile",
    )

    class FakeService:
        def __init__(self, **_kwargs) -> None:
            pass

        def sync_steam(self, *, steam_id: str) -> SyncOutcome:
            return fake_outcome

    monkeypatch.setattr(
        library_api, "_build_sync_service", lambda session: FakeService()
    )

    client = _make_client_with_session(db_session)
    res = client.post("/api/library/sync/steam", json={"steam_id": "76561198000000000"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "private_profile"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_library_api.py -k error_code -v`
Expected: FAIL (`error_code` not in response).

- [ ] **Step 3: Implement**

In `backend/app/api/library.py`, add the field to `SyncOutcomeOut`:

```python
class SyncOutcomeOut(BaseModel):
    run_id: int
    status: str
    counts: dict
    error: str | None
    error_code: str | None
```

In the `sync_steam` route, pass it through:

```python
    return SyncOutcomeOut(
        run_id=outcome.run_id,
        status=outcome.status,
        counts=outcome.counts,
        error=outcome.error,
        error_code=outcome.error_code,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_library_api.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
cd /c/dev/what-should-i-play && git add backend/app/api/library.py backend/tests/test_library_api.py
git commit -m "feat: expose error_code in sync-steam API response"
```

---

## Task 4: Preferences model — onboarding_completed column + migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/alembic/versions/0002_onboarding.py`
- Test: `backend/tests/test_repositories.py` (model-level assertion)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_repositories.py`:

```python
def test_preferences_defaults_onboarding_incomplete(db_session) -> None:
    from app.db.repositories import PreferencesRepository

    prefs = PreferencesRepository(db_session).get_or_create()
    db_session.commit()
    assert prefs.onboarding_completed is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_repositories.py -k onboarding_incomplete -v`
Expected: FAIL (`Preferences` has no attribute `onboarding_completed`).

- [ ] **Step 3: Add the column**

In `backend/app/db/models.py`, in the `Preferences` class, add after `difficulty_pref`:

```python
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
```

Ensure `text` is imported. Check the top-of-file SQLAlchemy import line; if `text` is absent, add it:

```python
from sqlalchemy import text
```

(`Boolean` is already imported — it's used by `RecommendationEvent.cache_hit`.)

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_repositories.py -k onboarding_incomplete -v`
Expected: PASS (conftest builds tables from the model, so the column exists).

- [ ] **Step 5: Create the Alembic migration (SQLite-safe batch)**

Create `backend/alembic/versions/0002_onboarding.py`:

```python
"""add onboarding_completed to preferences

Revision ID: 0002_onboarding
Revises: f402f3909114
Create Date: 2026-05-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_onboarding"
down_revision: Union[str, Sequence[str], None] = "f402f3909114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "onboarding_completed",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("onboarding_completed")
```

- [ ] **Step 6: Verify the migration round-trips on a scratch DB**

Run (uses a throwaway DB so your real `wsip.db` is untouched):

```bash
cd /c/dev/what-should-i-play/backend && DATABASE_URL="sqlite:///./_mig_check.db" .venv/Scripts/python.exe -m alembic upgrade head && DATABASE_URL="sqlite:///./_mig_check.db" .venv/Scripts/python.exe -m alembic downgrade base && DATABASE_URL="sqlite:///./_mig_check.db" .venv/Scripts/python.exe -m alembic upgrade head
```

Expected: all three commands succeed with no error. Then remove the scratch DB:

```bash
cd /c/dev/what-should-i-play/backend && rm -f _mig_check.db
```

(If `DATABASE_URL` is not read by `alembic/env.py`, instead run the plain `alembic upgrade head && alembic downgrade base && alembic upgrade head` against the configured DB — this is exactly what CI does — then verify your real data is intact via `GET /api/library`.)

- [ ] **Step 7: Apply the migration to the real dev DB**

```bash
cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m alembic upgrade head
```

Expected: `Running upgrade f402f3909114 -> 0002_onboarding`.

- [ ] **Step 8: Commit**

```bash
cd /c/dev/what-should-i-play && git add backend/app/db/models.py backend/alembic/versions/0002_onboarding.py backend/tests/test_repositories.py
git commit -m "feat: add onboarding_completed column to preferences (+ batch migration)"
```

---

## Task 5: PreferencesRepository — onboarding get/set

**Files:**
- Modify: `backend/app/db/repositories.py`
- Test: `backend/tests/test_repositories.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_repositories.py`:

```python
def test_onboarding_get_set_roundtrip(db_session) -> None:
    from app.db.repositories import PreferencesRepository

    repo = PreferencesRepository(db_session)
    assert repo.get_onboarding_completed() is False
    repo.set_onboarding_completed(True)
    db_session.commit()
    assert repo.get_onboarding_completed() is True


def test_preferences_update_preserves_onboarding_flag(db_session) -> None:
    from app.db.repositories import PreferencesRepository

    repo = PreferencesRepository(db_session)
    repo.set_onboarding_completed(True)
    db_session.commit()

    repo.update(
        liked_genres=["RPG"],
        disliked_genres=[],
        liked_types=[],
        session_length_pref="short",
        difficulty_pref="any",
    )
    db_session.commit()
    assert repo.get_onboarding_completed() is True  # not clobbered by a prefs save
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_repositories.py -k "onboarding_get_set or preserves_onboarding" -v`
Expected: FAIL (`get_onboarding_completed` missing).

- [ ] **Step 3: Implement**

In `backend/app/db/repositories.py`, add two methods to `PreferencesRepository` (after `update`):

```python
    def get_onboarding_completed(self) -> bool:
        return self.get_or_create().onboarding_completed

    def set_onboarding_completed(self, value: bool) -> None:
        prefs = self.get_or_create()
        prefs.onboarding_completed = value
        self._session.flush()
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_repositories.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
cd /c/dev/what-should-i-play && git add backend/app/db/repositories.py backend/tests/test_repositories.py
git commit -m "feat: PreferencesRepository onboarding get/set"
```

---

## Task 6: Onboarding API router

**Files:**
- Create: `backend/app/api/onboarding.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_onboarding_api.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_onboarding_api.py`:

```python
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.main import create_app


def _client(db_session: Session) -> TestClient:
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[deps.get_db_session] = _override
    return TestClient(app)


def test_get_onboarding_defaults_false(db_session: Session) -> None:
    res = _client(db_session).get("/api/onboarding")
    assert res.status_code == 200
    assert res.json() == {"completed": False}


def test_put_onboarding_persists(db_session: Session) -> None:
    client = _client(db_session)
    res = client.put("/api/onboarding", json={"completed": True})
    assert res.status_code == 200
    assert res.json() == {"completed": True}
    assert client.get("/api/onboarding").json() == {"completed": True}


def test_saving_preferences_does_not_reset_onboarding(db_session: Session) -> None:
    client = _client(db_session)
    client.put("/api/onboarding", json={"completed": True})
    client.put(
        "/api/preferences",
        json={
            "liked_genres": ["RPG"],
            "disliked_genres": [],
            "liked_types": [],
            "session_length_pref": "any",
            "difficulty_pref": "any",
        },
    )
    assert client.get("/api/onboarding").json() == {"completed": True}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest tests/test_onboarding_api.py -v`
Expected: FAIL (`/api/onboarding` 404 / module missing).

- [ ] **Step 3: Create the router**

Create `backend/app/api/onboarding.py`:

```python
"""HTTP endpoints for first-run onboarding state (stored on the Preferences row)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.db.repositories import PreferencesRepository

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingStatus(BaseModel):
    completed: bool


@router.get("", response_model=OnboardingStatus)
def get_onboarding(session: Session = Depends(get_db_session)) -> OnboardingStatus:
    completed = PreferencesRepository(session).get_onboarding_completed()
    session.commit()
    return OnboardingStatus(completed=completed)


@router.put("", response_model=OnboardingStatus)
def put_onboarding(
    body: OnboardingStatus, session: Session = Depends(get_db_session)
) -> OnboardingStatus:
    PreferencesRepository(session).set_onboarding_completed(body.completed)
    session.commit()
    return OnboardingStatus(completed=body.completed)
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, extend the API import and include it:

```python
from app.api import health, library, onboarding, preferences
```

```python
    app.include_router(preferences.router)
    app.include_router(onboarding.router)
```

- [ ] **Step 5: Run to verify pass + full suite**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (whole suite green).

- [ ] **Step 6: Lint + commit**

```bash
cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m ruff check .
```

```bash
cd /c/dev/what-should-i-play && git add backend/app/api/onboarding.py backend/app/main.py backend/tests/test_onboarding_api.py
git commit -m "feat: add onboarding GET/PUT API"
```

---

## Task 7: Frontend API client + pure onboardingMessages (TDD)

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/onboardingMessages.ts`, `frontend/src/lib/onboardingMessages.test.ts`

- [ ] **Step 1: Extend the API client**

Append to `frontend/src/lib/api.ts`:

```ts
export interface OnboardingStatus {
  completed: boolean;
}

export interface SyncResult {
  run_id: number;
  status: "ok" | "partial" | "failed";
  counts: Record<string, number>;
  error: string | null;
  error_code: string | null;
}

export const getOnboarding = () => apiGet<OnboardingStatus>("/api/onboarding");
export const setOnboarding = (completed: boolean) =>
  apiPut<OnboardingStatus>("/api/onboarding", { completed });
export const syncSteam = (steamId?: string) =>
  apiPost<SyncResult>(
    "/api/library/sync/steam",
    steamId ? { steam_id: steamId } : {},
  );
```

- [ ] **Step 2: Write the failing Vitest spec**

Create `frontend/src/lib/onboardingMessages.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { messageForErrorCode } from "@/lib/onboardingMessages";

describe("messageForErrorCode", () => {
  it("offers ID re-entry only for invalid_steamid", () => {
    expect(messageForErrorCode("invalid_steamid").allowIdReentry).toBe(true);
    expect(messageForErrorCode("private_profile").allowIdReentry).toBe(false);
    expect(messageForErrorCode("rate_limited").allowIdReentry).toBe(false);
    expect(messageForErrorCode("steam_auth").allowIdReentry).toBe(false);
  });

  it("gives a distinct title per known code", () => {
    const titles = [
      "private_profile",
      "invalid_steamid",
      "rate_limited",
      "steam_auth",
    ].map((c) => messageForErrorCode(c).title);
    expect(new Set(titles).size).toBe(4);
  });

  it("falls back for unknown or null codes", () => {
    expect(messageForErrorCode(null).title).toBe("Import failed");
    expect(messageForErrorCode("weird_code").title).toBe("Import failed");
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd /c/dev/what-should-i-play/frontend && npm run test`
Expected: FAIL (module `onboardingMessages` not found).

- [ ] **Step 4: Implement the pure module**

Create `frontend/src/lib/onboardingMessages.ts`:

```ts
export interface OnboardingErrorMessage {
  title: string;
  guidance: string;
  allowIdReentry: boolean;
}

export function messageForErrorCode(code: string | null): OnboardingErrorMessage {
  switch (code) {
    case "private_profile":
      return {
        title: "Your Steam profile is private",
        guidance:
          "Open Steam, go to Edit Profile then Privacy Settings, and set Game Details to Public. Then retry.",
        allowIdReentry: false,
      };
    case "invalid_steamid":
      return {
        title: "That Steam ID didn't work",
        guidance: "Double-check your 17-digit Steam ID and try again.",
        allowIdReentry: true,
      };
    case "rate_limited":
      return {
        title: "Steam is busy right now",
        guidance: "Steam is rate-limiting requests. Wait a moment, then retry.",
        allowIdReentry: false,
      };
    case "steam_auth":
      return {
        title: "Server Steam API key problem",
        guidance:
          "The Steam API key in backend/.env is missing or invalid. Fix it on the server, then retry.",
        allowIdReentry: false,
      };
    default:
      return {
        title: "Import failed",
        guidance: "Something went wrong talking to Steam. Retry, or skip for now.",
        allowIdReentry: false,
      };
  }
}
```

- [ ] **Step 5: Run to verify pass + build**

Run: `cd /c/dev/what-should-i-play/frontend && npm run test && npm run build`
Expected: tests PASS; build succeeds (zero TS errors).

- [ ] **Step 6: Commit**

```bash
cd /c/dev/what-should-i-play && git add frontend/src/lib/api.ts frontend/src/lib/onboardingMessages.ts frontend/src/lib/onboardingMessages.test.ts
git commit -m "feat: frontend onboarding API client + pure error-message mapping"
```

---

## Task 8: Extract shared PreferencesForm; refactor PreferencesPage

**Files:**
- Create: `frontend/src/components/PreferencesForm.tsx`
- Modify: `frontend/src/pages/PreferencesPage.tsx`

- [ ] **Step 1: Create the controlled PreferencesForm**

Create `frontend/src/components/PreferencesForm.tsx`:

```tsx
import type { Preferences } from "@/lib/api";
import { Button } from "@/components/ui/button";

const GENRES = [
  "RPG",
  "Shooter",
  "Strategy",
  "Roguelike",
  "Platformer",
  "Simulation",
  "Sports",
  "Puzzle",
  "Adventure",
  "Fighting",
];
const TYPES = ["singleplayer", "multiplayer", "co-op", "competitive"];
const SESSION_LENGTHS = ["any", "short", "medium", "long"];
const DIFFICULTIES = ["any", "easy", "medium", "hard"];

function toggle(list: string[], v: string): string[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

function Chips({
  options,
  selected,
  onToggle,
}: {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <Button
          key={o}
          size="sm"
          variant={selected.includes(o) ? "default" : "outline"}
          onClick={() => onToggle(o)}
        >
          {o}
        </Button>
      ))}
    </div>
  );
}

interface Props {
  value: Preferences;
  onChange: (next: Preferences) => void;
}

export default function PreferencesForm({ value, onChange }: Props) {
  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <h2 className="font-medium">Genres you like</h2>
        <Chips
          options={GENRES}
          selected={value.liked_genres}
          onToggle={(v) =>
            onChange({ ...value, liked_genres: toggle(value.liked_genres, v) })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Genres you dislike</h2>
        <Chips
          options={GENRES}
          selected={value.disliked_genres}
          onToggle={(v) =>
            onChange({
              ...value,
              disliked_genres: toggle(value.disliked_genres, v),
            })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Types you enjoy</h2>
        <Chips
          options={TYPES}
          selected={value.liked_types}
          onToggle={(v) =>
            onChange({ ...value, liked_types: toggle(value.liked_types, v) })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Preferred session length</h2>
        <div className="flex flex-wrap gap-2">
          {SESSION_LENGTHS.map((o) => (
            <Button
              key={o}
              size="sm"
              variant={value.session_length_pref === o ? "default" : "outline"}
              onClick={() => onChange({ ...value, session_length_pref: o })}
            >
              {o}
            </Button>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Preferred difficulty</h2>
        <div className="flex flex-wrap gap-2">
          {DIFFICULTIES.map((o) => (
            <Button
              key={o}
              size="sm"
              variant={value.difficulty_pref === o ? "default" : "outline"}
              onClick={() => onChange({ ...value, difficulty_pref: o })}
            >
              {o}
            </Button>
          ))}
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Refactor PreferencesPage to use it + add Re-run button**

Replace the entire contents of `frontend/src/pages/PreferencesPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPut, type Preferences } from "@/lib/api";
import PreferencesForm from "@/components/PreferencesForm";
import { Button } from "@/components/ui/button";

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saved, setSaved] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    apiGet<Preferences>("/api/preferences").then(setPrefs);
  }, []);

  if (!prefs) return <p>Loading preferences...</p>;

  const save = async () => {
    await apiPut("/api/preferences", prefs);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="max-w-2xl space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Preferences</h1>
        <Button variant="outline" size="sm" onClick={() => navigate("/onboarding")}>
          Re-run setup
        </Button>
      </div>

      <PreferencesForm value={prefs} onChange={setPrefs} />

      <div className="flex items-center gap-3">
        <Button onClick={save}>Save preferences</Button>
        {saved && <span className="text-sm text-green-600">Saved</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Build check**

Run: `cd /c/dev/what-should-i-play/frontend && npm run build`
Expected: build succeeds, zero TS errors.

- [ ] **Step 4: Commit**

```bash
cd /c/dev/what-should-i-play && git add frontend/src/components/PreferencesForm.tsx frontend/src/pages/PreferencesPage.tsx
git commit -m "refactor: extract shared PreferencesForm; add Re-run setup button"
```

---

## Task 9: OnboardingGuard + routing

**Files:**
- Create: `frontend/src/components/OnboardingGuard.tsx`
- Modify: `frontend/src/App.tsx`

This task adds the guard and the `/onboarding` route. It references `OnboardingWizard` (built in Task 10) — to keep this task self-contained and buildable, create a temporary placeholder wizard now; Task 10 replaces it.

- [ ] **Step 1: Temporary wizard placeholder (replaced in Task 10)**

Create `frontend/src/pages/OnboardingWizard.tsx`:

```tsx
export default function OnboardingWizard() {
  return <div className="min-h-screen p-8">Onboarding</div>;
}
```

- [ ] **Step 2: Create the guard**

Create `frontend/src/components/OnboardingGuard.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getOnboarding } from "@/lib/api";

export default function OnboardingGuard({ children }: { children: ReactNode }) {
  const [checked, setChecked] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    getOnboarding()
      .then((status) => {
        if (!status.completed && location.pathname !== "/onboarding") {
          navigate("/onboarding", { replace: true });
        }
      })
      .catch(() => {
        // If status can't be read, fail open and let the app render.
      })
      .finally(() => setChecked(true));
    // Run once on mount; redirect decision uses the entry pathname.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">
        Loading...
      </div>
    );
  }
  return <>{children}</>;
}
```

- [ ] **Step 3: Wire routing**

Replace `frontend/src/App.tsx`:

```tsx
import { Routes, Route } from "react-router-dom";
import OnboardingGuard from "@/components/OnboardingGuard";
import AppShell from "@/components/AppShell";
import LibraryPage from "@/pages/LibraryPage";
import PreferencesPage from "@/pages/PreferencesPage";
import OnboardingWizard from "@/pages/OnboardingWizard";

export default function App() {
  return (
    <OnboardingGuard>
      <Routes>
        <Route path="/onboarding" element={<OnboardingWizard />} />
        <Route element={<AppShell />}>
          <Route index element={<LibraryPage />} />
          <Route path="preferences" element={<PreferencesPage />} />
        </Route>
      </Routes>
    </OnboardingGuard>
  );
}
```

- [ ] **Step 4: Build check**

Run: `cd /c/dev/what-should-i-play/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/what-should-i-play && git add frontend/src/components/OnboardingGuard.tsx frontend/src/App.tsx frontend/src/pages/OnboardingWizard.tsx
git commit -m "feat: onboarding redirect guard + /onboarding route"
```

---

## Task 10: Onboarding wizard + steps

**Files:**
- Modify: `frontend/src/pages/OnboardingWizard.tsx`
- Create: `frontend/src/components/onboarding/WelcomeStep.tsx`, `ConnectStep.tsx`, `PreferencesStep.tsx`

- [ ] **Step 1: WelcomeStep**

Create `frontend/src/components/onboarding/WelcomeStep.tsx`:

```tsx
import { Button } from "@/components/ui/button";

export default function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="space-y-4 text-center">
      <h1 className="text-3xl font-semibold">Welcome to What Should I Play?</h1>
      <p className="text-muted-foreground">
        Import your Steam library, tell us what you enjoy, and get tailored
        picks for what to play next.
      </p>
      <Button onClick={onNext}>Get started</Button>
    </div>
  );
}
```

- [ ] **Step 2: ConnectStep (import + failure taxonomy + disable-while-pending)**

Create `frontend/src/components/onboarding/ConnectStep.tsx`:

```tsx
import { useState } from "react";
import { syncSteam, type SyncResult } from "@/lib/api";
import { messageForErrorCode } from "@/lib/onboardingMessages";
import { Button } from "@/components/ui/button";

export default function ConnectStep({ onNext }: { onNext: () => void }) {
  const [steamId, setSteamId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SyncResult | null>(null);

  const runImport = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await syncSteam(steamId.trim() || undefined);
      setResult(r);
    } catch {
      setResult({
        run_id: 0,
        status: "failed",
        counts: {},
        error: "Network error",
        error_code: "steam_error",
      });
    } finally {
      setBusy(false);
    }
  };

  const succeeded = result?.status === "ok" || result?.status === "partial";
  const added = (result?.counts.added ?? 0) + (result?.counts.updated ?? 0);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Connect your Steam library</h1>
        <p className="text-muted-foreground">
          Enter your 17-digit Steam ID, or leave it blank to use the ID from
          your server config.
        </p>
      </div>

      <input
        className="w-full rounded-md border border-border bg-background px-3 py-2"
        placeholder="Leave blank to use server-configured ID"
        value={steamId}
        onChange={(e) => setSteamId(e.target.value)}
      />

      <div className="flex items-center gap-3">
        <Button onClick={runImport} disabled={busy}>
          {busy ? "Importing your library..." : "Import library"}
        </Button>
      </div>

      {succeeded && (
        <div className="space-y-3 rounded-md border border-green-600/40 p-4">
          <p className="text-green-700">
            {added === 0
              ? "Connected - found 0 games in this library."
              : `Imported ${added} games.`}
          </p>
          {result?.status === "partial" && (
            <p className="text-sm text-muted-foreground">
              {result.counts.unmatched_igdb} game(s) couldn't be matched to rich
              metadata - they're still in your library.
            </p>
          )}
          <Button onClick={onNext}>Next</Button>
        </div>
      )}

      {result?.status === "failed" && (
        <FailureCard
          code={result.error_code}
          rawError={result.error}
          onRetry={runImport}
          onSkip={onNext}
        />
      )}
    </div>
  );
}

function FailureCard({
  code,
  rawError,
  onRetry,
  onSkip,
}: {
  code: string | null;
  rawError: string | null;
  onRetry: () => void;
  onSkip: () => void;
}) {
  const msg = messageForErrorCode(code);
  return (
    <div className="space-y-3 rounded-md border border-red-600/40 p-4">
      <p className="font-medium text-red-700">{msg.title}</p>
      <p className="text-sm text-muted-foreground">{msg.guidance}</p>
      {code === "steam_error" && rawError && (
        <p className="text-xs text-muted-foreground">Details: {rawError}</p>
      )}
      <div className="flex gap-3">
        <Button onClick={onRetry}>Retry</Button>
        <Button variant="outline" onClick={onSkip}>
          Skip import
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: PreferencesStep**

Create `frontend/src/components/onboarding/PreferencesStep.tsx`:

```tsx
import { useEffect, useState } from "react";
import { apiGet, apiPut, type Preferences } from "@/lib/api";
import PreferencesForm from "@/components/PreferencesForm";
import { Button } from "@/components/ui/button";

export default function PreferencesStep({ onFinish }: { onFinish: () => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiGet<Preferences>("/api/preferences").then(setPrefs);
  }, []);

  if (!prefs) return <p>Loading preferences...</p>;

  const finish = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await apiPut("/api/preferences", prefs);
      onFinish();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">What do you enjoy?</h1>
        <p className="text-muted-foreground">
          This helps tailor your recommendations. You can change it anytime.
        </p>
      </div>
      <PreferencesForm value={prefs} onChange={setPrefs} />
      <Button onClick={finish} disabled={saving}>
        Finish
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Wizard shell with step state + Skip setup**

Replace `frontend/src/pages/OnboardingWizard.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { setOnboarding } from "@/lib/api";
import { Button } from "@/components/ui/button";
import WelcomeStep from "@/components/onboarding/WelcomeStep";
import ConnectStep from "@/components/onboarding/ConnectStep";
import PreferencesStep from "@/components/onboarding/PreferencesStep";

type Step = "welcome" | "connect" | "preferences";
const ORDER: Step[] = ["welcome", "connect", "preferences"];

export default function OnboardingWizard() {
  const [step, setStep] = useState<Step>("welcome");
  const navigate = useNavigate();

  const complete = async () => {
    await setOnboarding(true);
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-6 py-3">
          <span className="text-sm text-muted-foreground">
            Step {ORDER.indexOf(step) + 1} of {ORDER.length}
          </span>
          <Button variant="ghost" size="sm" onClick={complete}>
            Skip setup
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-6 py-12">
        {step === "welcome" && <WelcomeStep onNext={() => setStep("connect")} />}
        {step === "connect" && (
          <ConnectStep onNext={() => setStep("preferences")} />
        )}
        {step === "preferences" && <PreferencesStep onFinish={complete} />}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Build check**

Run: `cd /c/dev/what-should-i-play/frontend && npm run build`
Expected: build succeeds, zero TS errors. (If `AppShell`/Button lack a `ghost` variant, use `variant="outline"` instead — check `src/components/ui/button.tsx` for the available variants before building.)

- [ ] **Step 6: Commit**

```bash
cd /c/dev/what-should-i-play && git add frontend/src/pages/OnboardingWizard.tsx frontend/src/components/onboarding
git commit -m "feat: onboarding wizard with welcome/connect/preferences steps"
```

---

## Task 11: Library page first-time empty state

**Files:**
- Modify: `frontend/src/pages/LibraryPage.tsx`

- [ ] **Step 1: Add the empty state**

In `frontend/src/pages/LibraryPage.tsx`:

Add `useNavigate` to the react-router import:

```tsx
import { useNavigate } from "react-router-dom";
```

Inside the component, add the hook near the other hooks:

```tsx
  const navigate = useNavigate();
```

Then, immediately after the existing `if (error) return ...` line and BEFORE the `return (` of the main grid, insert a whole-library empty check:

```tsx
  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-md space-y-4 py-16 text-center">
        <h1 className="text-2xl font-semibold">Your library is empty</h1>
        <p className="text-muted-foreground">
          Import your Steam games to start rating them and getting picks.
        </p>
        <Button onClick={() => navigate("/onboarding")}>Import from Steam</Button>
      </div>
    );
  }
```

(`Button` is already imported in this file. This whole-library check is distinct from the existing "No games match this filter." message, which still applies when filters exclude everything but the library is non-empty.)

- [ ] **Step 2: Build check**

Run: `cd /c/dev/what-should-i-play/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /c/dev/what-should-i-play && git add frontend/src/pages/LibraryPage.tsx
git commit -m "feat: first-time empty state on library page"
```

---

## Task 12: Final verification, docs, and PR

**Files:**
- Modify: `README.md`
- Modify: `~/.claude/projects/.../memory/project_what_should_i_play.md`

- [ ] **Step 1: Full backend verification**

Run: `cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check .`
Expected: all green (~75+ tests), ruff clean.

- [ ] **Step 2: Full frontend verification**

Run: `cd /c/dev/what-should-i-play/frontend && npm run build && npm run test`
Expected: build zero TS errors; Vitest all pass.

- [ ] **Step 3: Live smoke test (real backend)**

Start the backend, then exercise onboarding + a failure path against the real DB:

```bash
cd /c/dev/what-should-i-play/backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 > /tmp/uvicorn-2c.log 2>&1 &
for i in $(seq 1 20); do curl -s http://localhost:8000/api/health >/dev/null 2>&1 && break; sleep 0.5; done
echo "--- onboarding defaults ---"; curl -s http://localhost:8000/api/onboarding
echo; echo "--- set completed ---"; curl -s -X PUT http://localhost:8000/api/onboarding -H "Content-Type: application/json" -d '{"completed":true}'
echo; echo "--- bogus steam id surfaces an error_code ---"; curl -s -X POST http://localhost:8000/api/library/sync/steam -H "Content-Type: application/json" -d '{"steam_id":"123"}'
echo; echo "--- reset onboarding to false ---"; curl -s -X PUT http://localhost:8000/api/onboarding -H "Content-Type: application/json" -d '{"completed":false}'
echo
```

Expected: `{"completed":false}` then `{"completed":true}`; the bogus-id sync returns `status:"failed"` with a non-null `error_code` (likely `invalid_steamid` or `private_profile`); final reset to `{"completed":false}`. Then stop the server:

```bash
taskkill //F //IM python.exe >/dev/null 2>&1 || pkill -f "uvicorn app.main:app" 2>/dev/null; echo stopped
```

(Resetting onboarding to `false` leaves the dev app in first-run state so you can manually click through the wizard if desired.)

- [ ] **Step 4: Manual UI walk-through (optional but recommended)**

`npm run dev` from repo root, open http://localhost:5173:
1. With onboarding `false`, the app redirects to `/onboarding`.
2. Welcome -> Get started -> Connect: click Import (blank ID uses server config) -> success counts -> Next.
3. Set preferences -> Finish -> lands on Library with games.
4. Go to Preferences -> "Re-run setup" -> wizard reappears.
5. (Failure path) On Connect, type `123` as the ID and Import -> a failure card with Retry + Skip import.

- [ ] **Step 5: Update README**

In `README.md`, update the `## Status` section to note that first-run onboarding (Welcome -> Connect Steam -> Preferences), first-run detection, and Steam-failure handling now ship, and that the Steam import is now triggerable from the UI (no curl needed). Mention the new `GET|PUT /api/onboarding` endpoint and the `error_code` field on the sync response.

- [ ] **Step 6: Update memory file**

In `~/.claude/projects/C--Users-noman-OneDrive-Documents-Claude-Claude-Test/memory/project_what_should_i_play.md`, mark Sub-plan 2c COMPLETE: onboarding wizard + first-run flag (`onboarding_completed` on Preferences, `GET|PUT /api/onboarding`) + Steam `error_code` taxonomy (`private_profile`/`invalid_steamid`/`rate_limited`/`steam_auth`/`steam_error`) + `SteamAuthError` + public-empty-library success + shared `PreferencesForm` + library empty state. Next: Sub-plan 3 (heuristic "For You" v0 + telemetry).

- [ ] **Step 7: Commit, push, PR**

```bash
cd /c/dev/what-should-i-play && git add README.md
git commit -m "docs: mark Sub-plan 2c complete (onboarding + Steam-failure UX)"
git push -u origin <branch>
```

Then open a PR against `main` titled "Sub-plan 2c: onboarding + first-run + Steam-failure UX" summarizing the wizard, the `error_code` taxonomy, the onboarding flag, and the shared-form refactor. Confirm CI (backend ruff + alembic round-trip + pytest; frontend build + Vitest) is green. (The memory file lives outside the repo — edit it but do not git-add it.)

---

## Final verification checklist

- [ ] Backend `pytest` green; `ruff` clean.
- [ ] Alembic `upgrade -> downgrade -> upgrade` round-trips (CI runs this — the batch migration must not error on SQLite).
- [ ] Frontend `npm run build` zero TS errors; `npm run test` green.
- [ ] Live smoke: onboarding GET/PUT toggles; a bogus Steam ID returns a non-null `error_code`.
- [ ] Manual: first-run redirect, import success, a failure card, finish -> library, re-run from Preferences, empty-state CTA.
- [ ] CI green on the PR.

---

## Self-Review notes

- **Spec coverage:** wizard 3 steps (Tasks 9-10) ✅; first-run flag + guard (Tasks 4-6, 9) ✅; error_code taxonomy + SteamAuthError + empty-library success + narrow wrapping (Tasks 1-3) ✅; onboarding endpoint (Task 6) ✅; shared PreferencesForm + Re-run button (Task 8) ✅; library empty state (Task 11) ✅; pure onboardingMessages + Vitest (Task 7) ✅; SQLite-safe batch migration (Task 4) ✅; disable-while-pending on Import/Finish (Task 10) ✅; "Skip import" advances to preferences, "Skip setup" completes (Task 10) ✅.
- **Type consistency:** `SyncOutcome.error_code` (Task 2) ↔ `SyncOutcomeOut.error_code` (Task 3) ↔ TS `SyncResult.error_code` (Task 7); `OnboardingStatus {completed}` matches backend Pydantic model (Task 6) and TS interface (Task 7); `messageForErrorCode` codes match the backend `_error_code_for` outputs exactly (`private_profile`, `steam_auth`, `rate_limited`, `invalid_steamid`, `steam_error`).
- **No placeholders:** every code step is complete; the only intentional deferral is the Task 9 temporary wizard placeholder, explicitly replaced in Task 10.
- **Known limitation (carried from spec):** `invalid_steamid` is a best-effort 5xx heuristic; a malformed-but-parseable ID may surface as `private_profile`. Documented, not fixed.
- **Test-infra stance:** backend full red-green TDD; frontend Vitest covers the pure `onboardingMessages` mapping; wizard/guard components verified via `vite build` + manual walk-through (no component test runner — the accepted 2b trade-off).

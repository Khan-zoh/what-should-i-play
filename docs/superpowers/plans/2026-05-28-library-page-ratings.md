# Library Page + Ratings UI Implementation Plan (Sub-plan 2b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the imported Steam library into an interactive product page where the user can view every owned game, rate it (Loved/Liked/Meh/Disliked/Hated), set a play-status, and edit genre/type preferences — all persisted to SQLite.

**Architecture:** Add three new repositories (Rating, UserGameState, Preferences) following the existing repository-only-touches-ORM rule. Extend the library listing query with LEFT JOINs so a single `GET /api/library` call returns each game's rating + status. Add thin REST endpoints for upserting ratings, status, and preferences. On the frontend, introduce React Router with an app shell, a Library page rendering a responsive card grid, a rating control mapping human labels to 1–5 integers, and a quick-rate Sheet side panel that uses optimistic updates with rollback on failure.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2, Pydantic v2, pytest, respx (already present). Frontend — React 18, Vite, TypeScript (strict), Tailwind v3, shadcn/ui (Radix + cva), react-router-dom (new), lucide-react.

**Scope boundary:** Onboarding wizard, first-run detection, and Steam-failure UX are explicitly OUT of scope — they ship in Sub-plan 2c. This plan assumes a library has already been imported (it has: 23 real games). Manual game entry, the "For You" surface, and the mood quiz are later sub-plans.

**Revisions (post Codex review, 2026-05-28):** folded in 7 hardening changes — game-existence 404 guard on rating/status routes (Task 5); shared `get_db_session` extracted to `app/api/deps.py` (Tasks 5–6); shared `VALID_GAME_STATUSES` constant in models (Task 5); disable-while-pending on optimistic mutations (Task 10); render the missing session-length/difficulty controls on the preferences page (Task 11); pin the shadcn CLI command for reproducibility (Task 8); a new Vitest task covering the pure `ratings.ts` mapping (Task 12); and doc/memory update resequenced after final verification (now Task 13). Rejected: a service layer for single-table CRUD (over-engineering vs. existing 2a pattern), restricting the repo's nullable `enjoyment`, and Playwright/e2e in CI (too heavy for a localhost single-user surface).

---

## File Structure

**Backend (create):**
- `backend/app/db/repositories.py` — extend with `RatingRepository`, `UserGameStateRepository`, `PreferencesRepository`; extend `LibraryEntryRepository` with a rating/status-aware listing method; add `GameRepository.get`.
- `backend/app/db/models.py` — add the shared `VALID_GAME_STATUSES` frozenset next to the `UserGameState` enum comment.
- `backend/app/api/deps.py` — new: shared `get_db_session` dependency imported by both routers.
- `backend/app/api/library.py` — extend `LibraryItem` response; add rating + status routes; import `get_db_session` from `deps`.
- `backend/app/api/preferences.py` — new router for GET/PUT preferences; import `get_db_session` from `deps`.
- `backend/app/main.py` — register the preferences router.

**Backend (test):**
- `backend/tests/test_repositories.py` — extend with rating/state/preferences repo tests.
- `backend/tests/test_library_api.py` — extend with rating + status endpoint tests (incl. 404 on unknown game).
- `backend/tests/test_preferences_api.py` — new.

**Frontend (test):**
- `frontend/vitest.config.ts`, `frontend/src/lib/ratings.test.ts` — new: unit tests for the pure rating/status mapping.

**Frontend (create):**
- `frontend/package.json` — add `react-router-dom`.
- `frontend/src/components/ui/card.tsx`, `badge.tsx`, `select.tsx`, `sheet.tsx` — new shadcn primitives.
- `frontend/src/lib/api.ts` — extend with `apiPost`/`apiPut`/`apiDelete` + domain types.
- `frontend/src/lib/ratings.ts` — rating label ↔ value mapping (pure, unit-friendly).
- `frontend/src/components/AppShell.tsx` — nav + outlet.
- `frontend/src/components/GameCard.tsx` — single library card.
- `frontend/src/components/RatingControl.tsx` — five-button enjoyment control.
- `frontend/src/components/StatusSelect.tsx` — play-status dropdown.
- `frontend/src/components/QuickRatePanel.tsx` — Sheet side panel, optimistic.
- `frontend/src/pages/LibraryPage.tsx` — grid + filters/sort + panel wiring.
- `frontend/src/pages/PreferencesPage.tsx` — edit liked/disliked genres + types.
- `frontend/src/main.tsx` — wrap in `<BrowserRouter>`.
- `frontend/src/App.tsx` — replace health-check with `<Routes>`.

---

## Rating vocabulary (single source of truth)

Human label → stored integer (`ratings.enjoyment`):

| Label | Value |
|---|---|
| Loved | 5 |
| Liked | 4 |
| Meh | 3 |
| Disliked | 2 |
| Hated | 1 |
| Haven't played | (no rating row — DELETE) |

"Haven't played" is the absence of a `Rating` row, never a stored value. Selecting it deletes the row.

Play-status values (from `UserGameState.status`, reuse the model's enum comment): `backlog, installed, currently_playing, completed, abandoned, wishlisted, hidden, not_interested, want_to_replay, multiplayer_only, tried_and_refunded`. The UI surfaces a curated subset in 2b: `backlog, installed, currently_playing, completed, abandoned` (the rest are set by later surfaces). Unset status = no `UserGameState` row.

---

## Task 1: RatingRepository

**Files:**
- Modify: `backend/app/db/repositories.py`
- Test: `backend/tests/test_repositories.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_repositories.py`:

```python
def test_rating_repository_upsert_creates_then_updates(db_session) -> None:
    from app.db.repositories import GameRepository, RatingRepository

    g = GameRepository(db_session).upsert(
        igdb_id=1, steam_appid=10, name="Celeste", slug="celeste"
    )
    db_session.commit()
    repo = RatingRepository(db_session)

    created = repo.upsert(game_id=g.id, enjoyment=5, notes="great")
    db_session.commit()
    assert created.enjoyment == 5
    assert created.notes == "great"

    updated = repo.upsert(game_id=g.id, enjoyment=3, notes=None)
    db_session.commit()
    assert updated.id == created.id  # same row, not a new one
    assert updated.enjoyment == 3


def test_rating_repository_delete_removes_row(db_session) -> None:
    from app.db.repositories import GameRepository, RatingRepository

    g = GameRepository(db_session).upsert(
        igdb_id=2, steam_appid=20, name="Hades", slug="hades"
    )
    db_session.commit()
    repo = RatingRepository(db_session)
    repo.upsert(game_id=g.id, enjoyment=4, notes=None)
    db_session.commit()

    deleted = repo.delete(game_id=g.id)
    db_session.commit()
    assert deleted is True
    assert repo.get(game_id=g.id) is None

    # Deleting a non-existent rating is a no-op returning False.
    assert repo.delete(game_id=g.id) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k rating_repository -v`
Expected: FAIL with `ImportError: cannot import name 'RatingRepository'`.

- [ ] **Step 3: Implement RatingRepository**

In `backend/app/db/repositories.py`, update the import line and append the class:

```python
from app.db.models import (
    DataSyncRun,
    Game,
    LibraryEntry,
    Preferences,
    Rating,
    UserGameState,
)
```

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k rating_repository -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories.py backend/tests/test_repositories.py
git commit -m "feat: add RatingRepository with upsert/get/delete"
```

---

## Task 2: UserGameStateRepository

**Files:**
- Modify: `backend/app/db/repositories.py`
- Test: `backend/tests/test_repositories.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_repositories.py`:

```python
def test_state_repository_set_creates_then_updates(db_session) -> None:
    from app.db.repositories import GameRepository, UserGameStateRepository

    g = GameRepository(db_session).upsert(
        igdb_id=3, steam_appid=30, name="Stardew Valley", slug="stardew-valley"
    )
    db_session.commit()
    repo = UserGameStateRepository(db_session)

    created = repo.set_status(game_id=g.id, status="backlog")
    db_session.commit()
    assert created.status == "backlog"

    updated = repo.set_status(game_id=g.id, status="currently_playing")
    db_session.commit()
    assert updated.game_id == g.id  # PK is game_id; same row
    assert updated.status == "currently_playing"


def test_state_repository_clear_removes_row(db_session) -> None:
    from app.db.repositories import GameRepository, UserGameStateRepository

    g = GameRepository(db_session).upsert(
        igdb_id=4, steam_appid=40, name="Tunic", slug="tunic"
    )
    db_session.commit()
    repo = UserGameStateRepository(db_session)
    repo.set_status(game_id=g.id, status="completed")
    db_session.commit()

    assert repo.clear(game_id=g.id) is True
    db_session.commit()
    assert repo.get(game_id=g.id) is None
    assert repo.clear(game_id=g.id) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k state_repository -v`
Expected: FAIL with `ImportError: cannot import name 'UserGameStateRepository'`.

- [ ] **Step 3: Implement UserGameStateRepository**

Append to `backend/app/db/repositories.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k state_repository -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories.py backend/tests/test_repositories.py
git commit -m "feat: add UserGameStateRepository with set_status/clear"
```

---

## Task 3: PreferencesRepository

**Files:**
- Modify: `backend/app/db/repositories.py`
- Test: `backend/tests/test_repositories.py`

The `Preferences` table is a singleton: always row `id=1`. `get_or_create` returns it, creating defaults on first access.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_repositories.py`:

```python
def test_preferences_get_or_create_returns_singleton(db_session) -> None:
    from app.db.repositories import PreferencesRepository

    repo = PreferencesRepository(db_session)
    p1 = repo.get_or_create()
    db_session.commit()
    assert p1.id == 1
    assert p1.liked_genres == []
    assert p1.session_length_pref == "any"

    p2 = repo.get_or_create()
    assert p2.id == 1  # no second row


def test_preferences_update_persists_fields(db_session) -> None:
    from app.db.repositories import PreferencesRepository

    repo = PreferencesRepository(db_session)
    repo.get_or_create()
    db_session.commit()

    updated = repo.update(
        liked_genres=["RPG", "Roguelike"],
        disliked_genres=["Sports"],
        liked_types=["singleplayer"],
        session_length_pref="short",
        difficulty_pref="any",
    )
    db_session.commit()
    assert updated.liked_genres == ["RPG", "Roguelike"]
    assert updated.disliked_genres == ["Sports"]
    assert updated.session_length_pref == "short"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k preferences -v`
Expected: FAIL with `ImportError: cannot import name 'PreferencesRepository'`.

- [ ] **Step 3: Implement PreferencesRepository**

Append to `backend/app/db/repositories.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k preferences -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories.py backend/tests/test_repositories.py
git commit -m "feat: add PreferencesRepository singleton get_or_create/update"
```

---

## Task 4: Library listing with rating + status

**Files:**
- Modify: `backend/app/db/repositories.py` (`LibraryEntryRepository`)
- Test: `backend/tests/test_repositories.py`

Extend the listing to LEFT JOIN `ratings` and `user_game_state` so the API can return everything in one query. Returns a list of 4-tuples `(LibraryEntry, Game, Rating | None, UserGameState | None)`. Keep the existing `list_all_with_games` method as-is (the sync endpoint may still use it); add a new method.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_repositories.py`:

```python
def test_library_list_with_user_data_left_joins(db_session) -> None:
    from app.db.repositories import (
        GameRepository,
        LibraryEntryRepository,
        RatingRepository,
        UserGameStateRepository,
    )

    games = GameRepository(db_session)
    lib = LibraryEntryRepository(db_session)

    rated = games.upsert(igdb_id=1, steam_appid=10, name="A", slug="a")
    bare = games.upsert(igdb_id=2, steam_appid=20, name="B", slug="b")
    db_session.commit()
    lib.upsert(game_id=rated.id, source="steam", external_id="10", hours_played=5.0)
    lib.upsert(game_id=bare.id, source="steam", external_id="20", hours_played=0.0)
    db_session.commit()
    RatingRepository(db_session).upsert(game_id=rated.id, enjoyment=5, notes=None)
    UserGameStateRepository(db_session).set_status(
        game_id=rated.id, status="completed"
    )
    db_session.commit()

    rows = lib.list_with_user_data()
    by_name = {g.name: (entry, g, rating, state) for entry, g, rating, state in rows}

    assert by_name["A"][2].enjoyment == 5
    assert by_name["A"][3].status == "completed"
    assert by_name["B"][2] is None  # no rating row
    assert by_name["B"][3] is None  # no state row
    assert len(rows) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k list_with_user_data -v`
Expected: FAIL with `AttributeError: 'LibraryEntryRepository' object has no attribute 'list_with_user_data'`.

- [ ] **Step 3: Implement list_with_user_data**

In `repositories.py`, add `Rating` and `UserGameState` to the model import (done in Task 1) and add this method to `LibraryEntryRepository`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_repositories.py -k list_with_user_data -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories.py backend/tests/test_repositories.py
git commit -m "feat: add library listing with rating+status left joins"
```

---

## Task 5: Library API — rating + status fields and routes

**Files:**
- Modify: `backend/app/api/library.py`
- Test: `backend/tests/test_library_api.py`

Extend `LibraryItem` with `enjoyment: int | None` and `status: str | None`, switch `list_library` to `list_with_user_data`, and add two routes:
- `POST /api/library/games/{game_id}/rating` body `{enjoyment, notes?}` — upsert; `enjoyment=null` deletes; 404 if game unknown.
- `PUT /api/library/games/{game_id}/status` body `{status}` — set; `status=null` clears; 404 if game unknown.

- [ ] **Step 0: Add the shared status constant and `GameRepository.get`**

In `backend/app/db/models.py`, next to the `UserGameState.status` enum comment, add:

```python
VALID_GAME_STATUSES = frozenset(
    {
        "backlog",
        "installed",
        "currently_playing",
        "completed",
        "abandoned",
        "wishlisted",
        "hidden",
        "not_interested",
        "want_to_replay",
        "multiplayer_only",
        "tried_and_refunded",
    }
)
```

In `backend/app/db/repositories.py`, add a `get` method to `GameRepository` (used by the 404 guard):

```python
    def get(self, game_id: int) -> Game | None:
        return self._session.get(Game, game_id)
```

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_library_api.py`:

```python
def _seed_game(db_session: Session, *, igdb_id: int, appid: int, name: str, slug: str):
    g = GameRepository(db_session).upsert(
        igdb_id=igdb_id, steam_appid=appid, name=name, slug=slug
    )
    db_session.commit()
    LibraryEntryRepository(db_session).upsert(
        game_id=g.id, source="steam", external_id=str(appid), hours_played=1.0
    )
    db_session.commit()
    return g


def test_get_library_includes_rating_and_status(db_session: Session) -> None:
    from app.db.repositories import RatingRepository, UserGameStateRepository

    g = _seed_game(db_session, igdb_id=1, appid=10, name="A", slug="a")
    RatingRepository(db_session).upsert(game_id=g.id, enjoyment=4, notes=None)
    UserGameStateRepository(db_session).set_status(game_id=g.id, status="backlog")
    db_session.commit()

    client = _make_client_with_session(db_session)
    item = client.get("/api/library").json()[0]
    assert item["enjoyment"] == 4
    assert item["status"] == "backlog"


def test_post_rating_upserts_then_delete_on_null(db_session: Session) -> None:
    g = _seed_game(db_session, igdb_id=2, appid=20, name="B", slug="b")
    client = _make_client_with_session(db_session)

    res = client.post(
        f"/api/library/games/{g.id}/rating", json={"enjoyment": 5, "notes": "fav"}
    )
    assert res.status_code == 200
    assert res.json()["enjoyment"] == 5
    assert client.get("/api/library").json()[0]["enjoyment"] == 5

    res2 = client.post(f"/api/library/games/{g.id}/rating", json={"enjoyment": None})
    assert res2.status_code == 200
    assert res2.json()["enjoyment"] is None
    assert client.get("/api/library").json()[0]["enjoyment"] is None


def test_put_status_sets_then_clears_on_null(db_session: Session) -> None:
    g = _seed_game(db_session, igdb_id=3, appid=30, name="C", slug="c")
    client = _make_client_with_session(db_session)

    res = client.put(
        f"/api/library/games/{g.id}/status", json={"status": "currently_playing"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "currently_playing"

    res2 = client.put(f"/api/library/games/{g.id}/status", json={"status": None})
    assert res2.status_code == 200
    assert res2.json()["status"] is None
    assert client.get("/api/library").json()[0]["status"] is None


def test_rating_rejects_out_of_range(db_session: Session) -> None:
    g = _seed_game(db_session, igdb_id=4, appid=40, name="D", slug="d")
    client = _make_client_with_session(db_session)
    res = client.post(f"/api/library/games/{g.id}/rating", json={"enjoyment": 9})
    assert res.status_code == 422


def test_rating_unknown_game_returns_404(db_session: Session) -> None:
    client = _make_client_with_session(db_session)
    res = client.post("/api/library/games/99999/rating", json={"enjoyment": 5})
    assert res.status_code == 404


def test_status_unknown_game_returns_404(db_session: Session) -> None:
    client = _make_client_with_session(db_session)
    res = client.put("/api/library/games/99999/status", json={"status": "backlog"})
    assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_library_api.py -k "rating or status or includes" -v`
Expected: FAIL (routes 404 / missing fields).

- [ ] **Step 3: Implement the response field + routes**

In `backend/app/api/library.py`:

Add imports near the top. Note `get_db_session` now lives in `app/api/deps.py` (created in Task 6, but the import is added here — Task 6 must land the `deps.py` file; if executing strictly in order, create `deps.py` first per Task 6 Step 0). Remove the locally-defined `get_db_session` from `library.py`.

```python
from pydantic import BaseModel, Field

from app.api.deps import get_db_session
from app.db.models import VALID_GAME_STATUSES
from app.db.repositories import (
    GameRepository,
    LibraryEntryRepository,
    RatingRepository,
    SyncRunRepository,
    UserGameStateRepository,
)
```

Extend `LibraryItem` with two fields:

```python
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
```

Replace `list_library` body to use the joined query:

```python
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
```

Add request/response models and routes (place after the existing routes). The status whitelist now lives in `models.py` as `VALID_GAME_STATUSES` (Task 5 Step 0 below) — imported above, not redefined here.

```python
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
```

Note: the existing `from pydantic import BaseModel` import must be replaced by the `BaseModel, Field` import above (remove the old one to avoid a duplicate).

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: all prior tests + new ones PASS.

- [ ] **Step 5: Lint**

Run: `cd backend && .venv\Scripts\python.exe -m ruff check .`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/library.py backend/tests/test_library_api.py
git commit -m "feat: expose rating+status in library API with set routes"
```

---

## Task 6: Preferences API

**Files:**
- Create: `backend/app/api/deps.py`, `backend/app/api/preferences.py`
- Modify: `backend/app/api/library.py` (remove local `get_db_session`, import from deps), `backend/app/main.py`
- Test: `backend/tests/test_preferences_api.py`

- [ ] **Step 0: Extract the shared DB-session dependency**

Create `backend/app/api/deps.py`:

```python
"""Shared FastAPI dependencies. One `get_db_session` so all routers (and all
test overrides) reference the *same* dependency object."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

In `backend/app/api/library.py`, delete the locally-defined `get_db_session` function and rely on the `from app.api.deps import get_db_session` import added in Task 5. The existing override in `test_library_api.py` (`app.dependency_overrides[library_api.get_db_session]`) still resolves to the same object via the imported name — no change needed there.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_preferences_api.py`:

```python
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.main import create_app


def _client(db_session: Session) -> TestClient:
    app = create_app()

    def _override():
        yield db_session

    # Every router depends on the single shared deps.get_db_session, so one
    # override covers all routes.
    app.dependency_overrides[deps.get_db_session] = _override
    return TestClient(app)


def test_get_preferences_returns_defaults(db_session: Session) -> None:
    res = _client(db_session).get("/api/preferences")
    assert res.status_code == 200
    body = res.json()
    assert body["liked_genres"] == []
    assert body["session_length_pref"] == "any"


def test_put_preferences_persists(db_session: Session) -> None:
    client = _client(db_session)
    res = client.put(
        "/api/preferences",
        json={
            "liked_genres": ["RPG"],
            "disliked_genres": ["Sports"],
            "liked_types": ["singleplayer"],
            "session_length_pref": "short",
            "difficulty_pref": "any",
        },
    )
    assert res.status_code == 200
    assert res.json()["liked_genres"] == ["RPG"]
    # Persisted across requests.
    assert client.get("/api/preferences").json()["disliked_genres"] == ["Sports"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_preferences_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.preferences'`.

- [ ] **Step 3: Create the preferences router**

Create `backend/app/api/preferences.py`:

```python
"""HTTP endpoints for the singleton user preferences row."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.db.repositories import PreferencesRepository

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


class PreferencesModel(BaseModel):
    liked_genres: list[str]
    disliked_genres: list[str]
    liked_types: list[str]
    session_length_pref: str
    difficulty_pref: str


@router.get("", response_model=PreferencesModel)
def get_preferences(session: Session = Depends(get_db_session)) -> PreferencesModel:
    prefs = PreferencesRepository(session).get_or_create()
    session.commit()
    return PreferencesModel(
        liked_genres=prefs.liked_genres,
        disliked_genres=prefs.disliked_genres,
        liked_types=prefs.liked_types,
        session_length_pref=prefs.session_length_pref,
        difficulty_pref=prefs.difficulty_pref,
    )


@router.put("", response_model=PreferencesModel)
def put_preferences(
    body: PreferencesModel, session: Session = Depends(get_db_session)
) -> PreferencesModel:
    prefs = PreferencesRepository(session).update(
        liked_genres=body.liked_genres,
        disliked_genres=body.disliked_genres,
        liked_types=body.liked_types,
        session_length_pref=body.session_length_pref,
        difficulty_pref=body.difficulty_pref,
    )
    session.commit()
    return PreferencesModel(
        liked_genres=prefs.liked_genres,
        disliked_genres=prefs.disliked_genres,
        liked_types=prefs.liked_types,
        session_length_pref=prefs.session_length_pref,
        difficulty_pref=prefs.difficulty_pref,
    )
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, find where the library router is included and add the preferences router next to it:

```python
from app.api import preferences as preferences_api
...
app.include_router(preferences_api.router)
```

(Match the existing include style — if the file uses `from app.api.library import router as library_router`, mirror that.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_preferences_api.py -v`
Expected: PASS.

- [ ] **Step 6: Full suite + lint + commit**

```bash
cd backend && .venv\Scripts\python.exe -m pytest && .venv\Scripts\python.exe -m ruff check .
```

```bash
git add backend/app/api/preferences.py backend/app/main.py backend/tests/test_preferences_api.py
git commit -m "feat: add preferences GET/PUT API"
```

---

## Task 7: Frontend deps + router shell

**Files:**
- Modify: `frontend/package.json` (via npm)
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: Install react-router-dom**

Run: `cd frontend && npm install react-router-dom@^6`
Expected: adds dependency, no errors.

- [ ] **Step 2: Create the app shell**

Create `frontend/src/components/AppShell.tsx`:

```tsx
import { NavLink, Outlet } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
    isActive
      ? "bg-secondary text-secondary-foreground"
      : "text-muted-foreground hover:text-foreground"
  }`;

export default function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <nav className="mx-auto flex max-w-6xl items-center gap-2 px-6 py-3">
          <span className="mr-4 text-lg font-semibold">What Should I Play?</span>
          <NavLink to="/" className={linkClass} end>
            Library
          </NavLink>
          <NavLink to="/preferences" className={linkClass}>
            Preferences
          </NavLink>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Wire the router**

Replace `frontend/src/App.tsx`:

```tsx
import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/AppShell";
import LibraryPage from "@/pages/LibraryPage";
import PreferencesPage from "@/pages/PreferencesPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LibraryPage />} />
        <Route path="preferences" element={<PreferencesPage />} />
      </Route>
    </Routes>
  );
}
```

Wrap `main.tsx` in `<BrowserRouter>`. Edit `frontend/src/main.tsx` so the render call is:

```tsx
import { BrowserRouter } from "react-router-dom";
...
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
```

(Preserve the existing import style for React/createRoot already in the file.)

- [ ] **Step 4: Build check**

This will FAIL to compile until `LibraryPage`/`PreferencesPage` exist (Tasks 9 & 10). To keep this task self-contained, create minimal placeholders now:

`frontend/src/pages/LibraryPage.tsx`:

```tsx
export default function LibraryPage() {
  return <p>Library</p>;
}
```

`frontend/src/pages/PreferencesPage.tsx`:

```tsx
export default function PreferencesPage() {
  return <p>Preferences</p>;
}
```

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/main.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/pages/LibraryPage.tsx frontend/src/pages/PreferencesPage.tsx
git commit -m "feat: add react-router shell with Library/Preferences routes"
```

---

## Task 8: API client + rating mapping + shadcn primitives

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/ratings.ts`
- Create: `frontend/src/components/ui/card.tsx`, `badge.tsx`, `select.tsx`, `sheet.tsx`

- [ ] **Step 1: Extend the API client**

Append to `frontend/src/lib/api.ts`:

```ts
async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${method} ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export const apiPost = <T>(path: string, body?: unknown) =>
  apiSend<T>("POST", path, body);
export const apiPut = <T>(path: string, body?: unknown) =>
  apiSend<T>("PUT", path, body);

export interface LibraryItem {
  game_id: number;
  name: string;
  slug: string;
  steam_appid: number | null;
  igdb_id: number | null;
  hours_played: number;
  cover_url: string | null;
  critic_score: number | null;
  store_url: string | null;
  enjoyment: number | null;
  status: string | null;
}

export interface Preferences {
  liked_genres: string[];
  disliked_genres: string[];
  liked_types: string[];
  session_length_pref: string;
  difficulty_pref: string;
}
```

- [ ] **Step 2: Create the rating mapping**

Create `frontend/src/lib/ratings.ts`:

```ts
export const RATING_OPTIONS = [
  { label: "Loved", value: 5 },
  { label: "Liked", value: 4 },
  { label: "Meh", value: 3 },
  { label: "Disliked", value: 2 },
  { label: "Hated", value: 1 },
] as const;

export type RatingValue = 1 | 2 | 3 | 4 | 5;

export function labelForValue(value: number | null): string {
  if (value === null) return "Haven't played";
  return RATING_OPTIONS.find((o) => o.value === value)?.label ?? "Haven't played";
}

export const STATUS_OPTIONS = [
  { label: "Backlog", value: "backlog" },
  { label: "Installed", value: "installed" },
  { label: "Currently playing", value: "currently_playing" },
  { label: "Completed", value: "completed" },
  { label: "Abandoned", value: "abandoned" },
] as const;

export function labelForStatus(status: string | null): string {
  if (status === null) return "No status";
  return STATUS_OPTIONS.find((o) => o.value === status)?.label ?? status;
}
```

- [ ] **Step 3: Add shadcn primitives via the CLI (reproducible)**

Generate the four components with the pinned shadcn CLI rather than hand-copying from docs (avoids version drift between runs). From `frontend/`:

Run: `cd frontend && npx --yes shadcn@2.3.0 add card badge select sheet`
Expected: writes `src/components/ui/{card,badge,select,sheet}.tsx` and installs the needed Radix peers (`@radix-ui/react-select`, `@radix-ui/react-dialog`) into `package.json`.

Notes for the executing agent:
- If `components.json` does not yet exist, the CLI will prompt to create it — run `npx --yes shadcn@2.3.0 init` first, accepting: style "default", base color "slate", CSS variables yes, and the existing `@/` alias (matches `tsconfig`/`vite.config`).
- If the CLI is unavailable offline, fall back to copying the exact component source for these four from the shadcn/ui `v2.3.0` git tag (NOT "latest") so output is deterministic.
- All four import `cn` from `@/lib/utils` (already present).

After generation, verify the Radix peers landed:

Run: `cd frontend && npm ls @radix-ui/react-select @radix-ui/react-dialog`
Expected: both resolve with no "missing" errors.

- [ ] **Step 4: Build check**

Run: `cd frontend && npm run build`
Expected: build succeeds (components compile even if unused).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/ratings.ts frontend/src/components/ui frontend/package.json frontend/package-lock.json
git commit -m "feat: add API client mutations, rating mapping, shadcn primitives"
```

---

## Task 9: Rating control + status select + game card

**Files:**
- Create: `frontend/src/components/RatingControl.tsx`
- Create: `frontend/src/components/StatusSelect.tsx`
- Create: `frontend/src/components/GameCard.tsx`

These are presentational + callback-driven (no fetching inside). The page (Task 10) owns state and passes handlers down.

- [ ] **Step 1: RatingControl**

Create `frontend/src/components/RatingControl.tsx`:

```tsx
import { RATING_OPTIONS } from "@/lib/ratings";
import { Button } from "@/components/ui/button";

interface Props {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

export default function RatingControl({ value, onChange, disabled }: Props) {
  return (
    <div className="flex flex-wrap gap-1">
      {RATING_OPTIONS.map((opt) => (
        <Button
          key={opt.value}
          size="sm"
          disabled={disabled}
          variant={value === opt.value ? "default" : "outline"}
          onClick={() => onChange(value === opt.value ? null : opt.value)}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );
}
```

(Clicking the active rating again clears it = "Haven't played".)

- [ ] **Step 2: StatusSelect**

Create `frontend/src/components/StatusSelect.tsx`:

```tsx
import { STATUS_OPTIONS } from "@/lib/ratings";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const NONE = "__none__";

interface Props {
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
}

export default function StatusSelect({ value, onChange, disabled }: Props) {
  return (
    <Select
      value={value ?? NONE}
      disabled={disabled}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
    >
      <SelectTrigger className="w-44">
        <SelectValue placeholder="No status" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>No status</SelectItem>
        {STATUS_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

- [ ] **Step 3: GameCard**

Create `frontend/src/components/GameCard.tsx`:

```tsx
import type { LibraryItem } from "@/lib/api";
import { labelForStatus, labelForValue } from "@/lib/ratings";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Props {
  item: LibraryItem;
  onQuickRate: (item: LibraryItem) => void;
}

export default function GameCard({ item, onQuickRate }: Props) {
  return (
    <Card className="overflow-hidden flex flex-col">
      <div className="aspect-[3/4] bg-muted">
        {item.cover_url ? (
          <img
            src={item.cover_url}
            alt={item.name}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
            No cover
          </div>
        )}
      </div>
      <CardContent className="space-y-2 p-3">
        <h3 className="line-clamp-2 font-medium leading-tight">{item.name}</h3>
        <div className="flex flex-wrap gap-1 text-xs">
          <Badge variant="secondary">{item.hours_played.toFixed(0)}h</Badge>
          {item.enjoyment !== null && (
            <Badge>{labelForValue(item.enjoyment)}</Badge>
          )}
          {item.status !== null && (
            <Badge variant="outline">{labelForStatus(item.status)}</Badge>
          )}
        </div>
      </CardContent>
      <CardFooter className="mt-auto p-3 pt-0">
        <Button
          size="sm"
          variant="outline"
          className="w-full"
          onClick={() => onQuickRate(item)}
        >
          Rate / status
        </Button>
      </CardFooter>
    </Card>
  );
}
```

- [ ] **Step 4: Build check**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RatingControl.tsx frontend/src/components/StatusSelect.tsx frontend/src/components/GameCard.tsx
git commit -m "feat: add RatingControl, StatusSelect, GameCard components"
```

---

## Task 10: Library page with grid, filters, and optimistic quick-rate panel

**Files:**
- Create: `frontend/src/components/QuickRatePanel.tsx`
- Replace: `frontend/src/pages/LibraryPage.tsx`

- [ ] **Step 1: QuickRatePanel**

Create `frontend/src/components/QuickRatePanel.tsx`:

```tsx
import type { LibraryItem } from "@/lib/api";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import RatingControl from "@/components/RatingControl";
import StatusSelect from "@/components/StatusSelect";

interface Props {
  item: LibraryItem | null;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onRate: (item: LibraryItem, value: number | null) => void;
  onStatus: (item: LibraryItem, status: string | null) => void;
}

export default function QuickRatePanel({
  item,
  pending,
  onOpenChange,
  onRate,
  onStatus,
}: Props) {
  return (
    <Sheet open={item !== null} onOpenChange={onOpenChange}>
      <SheetContent>
        {item && (
          <>
            <SheetHeader>
              <SheetTitle>{item.name}</SheetTitle>
            </SheetHeader>
            <div className="mt-6 space-y-6">
              <div className="space-y-2">
                <p className="text-sm font-medium">How much did you enjoy it?</p>
                <RatingControl
                  value={item.enjoyment}
                  disabled={pending}
                  onChange={(v) => onRate(item, v)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Status</p>
                <StatusSelect
                  value={item.status}
                  disabled={pending}
                  onChange={(s) => onStatus(item, s)}
                />
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 2: LibraryPage with data + optimistic mutations**

Replace `frontend/src/pages/LibraryPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, apiPut, type LibraryItem } from "@/lib/api";
import GameCard from "@/components/GameCard";
import QuickRatePanel from "@/components/QuickRatePanel";
import { Button } from "@/components/ui/button";

type Sort = "name" | "hours" | "rating";

export default function LibraryPage() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("name");
  const [ratedOnly, setRatedOnly] = useState(false);
  const [active, setActive] = useState<LibraryItem | null>(null);
  // Game ids with an in-flight mutation; controls disable to avoid out-of-order
  // writes (single-user, but cheap correctness insurance).
  const [pending, setPending] = useState<ReadonlySet<number>>(new Set());

  const markPending = (gameId: number, on: boolean) =>
    setPending((prev) => {
      const next = new Set(prev);
      if (on) next.add(gameId);
      else next.delete(gameId);
      return next;
    });

  useEffect(() => {
    apiGet<LibraryItem[]>("/api/library")
      .then(setItems)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const patch = (gameId: number, fields: Partial<LibraryItem>) => {
    setItems((prev) =>
      prev.map((it) => (it.game_id === gameId ? { ...it, ...fields } : it)),
    );
    setActive((cur) =>
      cur && cur.game_id === gameId ? { ...cur, ...fields } : cur,
    );
  };

  const rate = async (item: LibraryItem, value: number | null) => {
    if (pending.has(item.game_id)) return;
    const prev = item.enjoyment;
    markPending(item.game_id, true);
    patch(item.game_id, { enjoyment: value }); // optimistic
    try {
      await apiPost(`/api/library/games/${item.game_id}/rating`, {
        enjoyment: value,
      });
    } catch {
      patch(item.game_id, { enjoyment: prev }); // rollback
    } finally {
      markPending(item.game_id, false);
    }
  };

  const setStatus = async (item: LibraryItem, status: string | null) => {
    if (pending.has(item.game_id)) return;
    const prev = item.status;
    markPending(item.game_id, true);
    patch(item.game_id, { status }); // optimistic
    try {
      await apiPut(`/api/library/games/${item.game_id}/status`, { status });
    } catch {
      patch(item.game_id, { status: prev }); // rollback
    } finally {
      markPending(item.game_id, false);
    }
  };

  const visible = useMemo(() => {
    const filtered = ratedOnly
      ? items.filter((i) => i.enjoyment !== null)
      : items;
    return [...filtered].sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "hours") return b.hours_played - a.hours_played;
      return (b.enjoyment ?? 0) - (a.enjoyment ?? 0);
    });
  }, [items, sort, ratedOnly]);

  if (loading) return <p>Loading library…</p>;
  if (error) return <p className="text-red-600">Failed to load: {error}</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">
          Library ({items.length})
        </h1>
        <Button
          size="sm"
          variant={ratedOnly ? "default" : "outline"}
          onClick={() => setRatedOnly((v) => !v)}
        >
          Rated only
        </Button>
        {(["name", "hours", "rating"] as Sort[]).map((s) => (
          <Button
            key={s}
            size="sm"
            variant={sort === s ? "default" : "outline"}
            onClick={() => setSort(s)}
          >
            {s === "name" ? "A–Z" : s === "hours" ? "Most played" : "Top rated"}
          </Button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="text-muted-foreground">No games match this filter.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {visible.map((item) => (
            <GameCard
              key={item.game_id}
              item={item}
              onQuickRate={setActive}
            />
          ))}
        </div>
      )}

      <QuickRatePanel
        item={active}
        pending={active ? pending.has(active.game_id) : false}
        onOpenChange={(open) => !open && setActive(null)}
        onRate={rate}
        onStatus={setStatus}
      />
    </div>
  );
}
```

- [ ] **Step 3: Build check**

Run: `cd frontend && npm run build`
Expected: build succeeds, zero TS errors.

- [ ] **Step 4: Manual end-to-end verification**

Run: `npm run dev` (from repo root). In the browser at http://localhost:5173:
1. Library grid shows the 23 imported games with covers, hours badges.
2. Click "Rate / status" → side panel opens → click "Loved" → badge appears on the card immediately.
3. Reload the page → the rating persists (came from the backend).
4. Set a status → reload → status persists.
5. Toggle "Rated only" and the sort buttons → grid updates.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/QuickRatePanel.tsx frontend/src/pages/LibraryPage.tsx
git commit -m "feat: library page with grid, filters, optimistic quick-rate panel"
```

---

## Task 11: Preferences page

**Files:**
- Replace: `frontend/src/pages/PreferencesPage.tsx`

A simple form: toggle genres in liked/disliked, toggle types liked, pick session length + difficulty, Save → PUT.

- [ ] **Step 1: Implement the page**

Replace `frontend/src/pages/PreferencesPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { apiGet, apiPut, type Preferences } from "@/lib/api";
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

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<Preferences>("/api/preferences").then(setPrefs);
  }, []);

  if (!prefs) return <p>Loading preferences…</p>;

  const save = async () => {
    await apiPut("/api/preferences", prefs);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const Chips = ({
    options,
    selected,
    onToggle,
  }: {
    options: string[];
    selected: string[];
    onToggle: (v: string) => void;
  }) => (
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

  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Preferences</h1>

      <section className="space-y-2">
        <h2 className="font-medium">Genres you like</h2>
        <Chips
          options={GENRES}
          selected={prefs.liked_genres}
          onToggle={(v) =>
            setPrefs({ ...prefs, liked_genres: toggle(prefs.liked_genres, v) })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Genres you dislike</h2>
        <Chips
          options={GENRES}
          selected={prefs.disliked_genres}
          onToggle={(v) =>
            setPrefs({
              ...prefs,
              disliked_genres: toggle(prefs.disliked_genres, v),
            })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Types you enjoy</h2>
        <Chips
          options={TYPES}
          selected={prefs.liked_types}
          onToggle={(v) =>
            setPrefs({ ...prefs, liked_types: toggle(prefs.liked_types, v) })
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
              variant={prefs.session_length_pref === o ? "default" : "outline"}
              onClick={() => setPrefs({ ...prefs, session_length_pref: o })}
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
              variant={prefs.difficulty_pref === o ? "default" : "outline"}
              onClick={() => setPrefs({ ...prefs, difficulty_pref: o })}
            >
              {o}
            </Button>
          ))}
        </div>
      </section>

      <div className="flex items-center gap-3">
        <Button onClick={save}>Save preferences</Button>
        {saved && <span className="text-sm text-green-600">Saved ✓</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build check**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual verification**

With `npm run dev` running: navigate to Preferences, toggle some genres, Save, reload → selections persist.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PreferencesPage.tsx
git commit -m "feat: preferences page wired to GET/PUT /api/preferences"
```

---

## Task 12: Vitest unit tests for the pure rating/status mapping

Per the Codex review, the `ratings.ts` mapping is pure logic that's cheap to test and easy to break (label↔value drift, null handling). Add a minimal Vitest setup covering only this module — no component/DOM/e2e tests (those stay deferred).

**Files:**
- Modify: `frontend/package.json` (add `vitest` + `test` script)
- Create: `frontend/vitest.config.ts`, `frontend/src/lib/ratings.test.ts`

- [ ] **Step 1: Install Vitest**

Run: `cd frontend && npm install -D vitest@^2`
Expected: adds `vitest` to devDependencies.

- [ ] **Step 2: Add the test script**

In `frontend/package.json`, add to `"scripts"`:

```json
    "test": "vitest run"
```

- [ ] **Step 3: Create the Vitest config**

Create `frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
```

- [ ] **Step 4: Write the failing tests**

Create `frontend/src/lib/ratings.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  RATING_OPTIONS,
  STATUS_OPTIONS,
  labelForStatus,
  labelForValue,
} from "@/lib/ratings";

describe("ratings mapping", () => {
  it("maps each value to its label", () => {
    expect(labelForValue(5)).toBe("Loved");
    expect(labelForValue(4)).toBe("Liked");
    expect(labelForValue(3)).toBe("Meh");
    expect(labelForValue(2)).toBe("Disliked");
    expect(labelForValue(1)).toBe("Hated");
  });

  it("treats null and unknown values as 'Haven't played'", () => {
    expect(labelForValue(null)).toBe("Haven't played");
    expect(labelForValue(99)).toBe("Haven't played");
  });

  it("covers exactly the five 1..5 values", () => {
    expect(RATING_OPTIONS.map((o) => o.value).sort()).toEqual([1, 2, 3, 4, 5]);
  });

  it("maps status values and falls back gracefully", () => {
    expect(labelForStatus("currently_playing")).toBe("Currently playing");
    expect(labelForStatus(null)).toBe("No status");
    expect(labelForStatus("unmapped")).toBe("unmapped");
  });

  it("status options are a subset of valid backend statuses", () => {
    const allowed = new Set([
      "backlog",
      "installed",
      "currently_playing",
      "completed",
      "abandoned",
    ]);
    for (const opt of STATUS_OPTIONS) expect(allowed.has(opt.value)).toBe(true);
  });
});
```

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm run test`
Expected: PASS (5 tests). If `ratings.ts` from Task 8 already exists, these pass immediately — they pin the contract against future edits.

- [ ] **Step 6: Wire Vitest into CI**

In the frontend CI job (`.github/workflows/*.yml`), add a step after the build that runs `npm run test`. Mirror the existing `npm run build` step's `working-directory: frontend` (or `cd frontend`) style. Keep it non-blocking-free: it should fail the job on test failure.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/lib/ratings.test.ts .github
git commit -m "test: add Vitest unit tests for ratings mapping + wire into CI"
```

---

## Final verification

- [ ] Backend: `cd backend && .venv\Scripts\python.exe -m pytest` → all green (≈62 tests).
- [ ] Backend: `.venv\Scripts\python.exe -m ruff check .` → clean.
- [ ] Frontend: `cd frontend && npm run build` → zero TS errors.
- [ ] Frontend: `cd frontend && npm run test` → 5 passed.
- [ ] Manual: `npm run dev`, rate a game, set status, edit preferences, reload — everything persists.

Only after every check above is green, proceed to Task 13.

---

## Task 13: Update docs + memory + push

**Files:**
- Modify: `README.md`
- Modify: `~/.claude/projects/.../memory/project_what_should_i_play.md`

- [ ] **Step 1: Update README status**

In `README.md`, update the `## Status` section to note the library page + ratings UI now ship, and add a "Daily commands" note that the frontend now has Library + Preferences pages and a `npm run test` (frontend) command.

- [ ] **Step 2: Update memory file**

In `project_what_should_i_play.md`, change the status block to: "Sub-plan 2b (library page + ratings + preferences UI) COMPLETE. Next: Sub-plan 2c — onboarding wizard + first-run detection + Steam-failure UX." Note the new endpoints (`POST /api/library/games/{id}/rating`, `PUT /api/library/games/{id}/status`, `GET|PUT /api/preferences`), the new frontend routes (Library `/`, Preferences `/preferences`), and that the frontend now has a Vitest suite.

- [ ] **Step 3: Commit and push**

```bash
git add README.md
git commit -m "docs: mark Sub-plan 2b complete, document ratings/preferences UI"
git push origin main
```

(The memory file lives outside the repo; edit it but do not git-add it.)

- [ ] **Step 4: Confirm CI**

Confirm GitHub Actions is green on `main` (ruff + alembic round-trip + pytest on backend; build + Vitest on frontend).

---

## Self-Review notes

- **Spec coverage:** ratings (Loved→Hated = 5→1, "Haven't played" = no row) ✅; status badges ✅; per-game persistence ✅; preferences (genres/types/session-length/difficulty) ✅. Onboarding + Steam-failure UX intentionally deferred to 2c.
- **Type consistency:** `LibraryItem` shape matches backend `LibraryItem` response (added `enjoyment`, `status`); `Preferences` TS interface matches `PreferencesModel`; rating values 1–5 enforced both server-side (`ge=1, le=5`) and via the fixed `RATING_OPTIONS` table; status validated against the shared `VALID_GAME_STATUSES` frozenset server-side and a curated `STATUS_OPTIONS` client-side.
- **No placeholders:** every backend step has full code; shadcn primitives (Task 8) are generated by the pinned `shadcn@2.3.0` CLI for reproducibility rather than hand-copied.
- **Hardening from Codex review (folded in):** 404 guards on rating/status routes (Task 5); shared `get_db_session` in `deps.py` (Tasks 5–6); shared `VALID_GAME_STATUSES` (Task 5); disable-while-pending optimistic mutations (Task 10); session-length/difficulty controls now rendered (Task 11); pinned shadcn CLI (Task 8); Vitest for pure `ratings.ts` logic (Task 12); docs resequenced after final verification (Task 13).
- **Test-infra stance (deliberate):** backend is full red-green TDD. Frontend adds a *scoped* Vitest suite for the pure mapping logic only; components/pages are verified via `vite build` + scripted manual checks. Rejected full e2e/Playwright-in-CI as too heavy for a localhost single-user surface — an explicit, defensible trade-off, not an oversight.

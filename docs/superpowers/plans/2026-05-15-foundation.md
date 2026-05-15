# Foundation + Schema Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the empty-but-runnable shell of the *What Should I Play?* application — FastAPI backend with SQLite + Alembic migrations for the stable-spine tables, a React + Vite + TypeScript + Tailwind + shadcn/ui frontend skeleton that successfully calls the backend, dev scripts that run both with one command, and CI that runs lint + tests + build on every push.

**Architecture:** Monorepo layout (`backend/` + `frontend/` + root scripts). FastAPI app exposes `/api/*` JSON routes. SQLAlchemy 2.x ORM with Alembic migrations. React frontend served separately in dev (Vite on 5173, FastAPI on 8000) with CORS configured. Subsystem-specific tables (`quiz_sessions`, `model_runs`, `play_sessions`) are deferred to their own sub-plans — this plan ships only the stable schema spine.

**Tech Stack:**
- Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pydantic-settings, uvicorn, pytest, httpx, ruff, mypy
- Node 20+, React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui (Radix + Tailwind), class-variance-authority, clsx, tailwind-merge, lucide-react
- SQLite (file-backed in dev, in-memory in tests)
- GitHub Actions for CI

---

## File Structure

This plan creates the following files. Each task says exactly which files it touches.

```
what-should-i-play/
├── .github/workflows/ci.yml
├── .gitignore
├── README.md
├── package.json                          # root: runs both stacks via `concurrently`
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_spine.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app factory
│   │   ├── config.py                     # Settings (pydantic-settings)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── health.py
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── base.py                   # DeclarativeBase
│   │       ├── session.py                # engine + SessionLocal
│   │       └── models.py                 # all spine ORM models
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_health.py
│       └── test_models.py
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── tsconfig.node.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── index.html
    ├── components.json                   # shadcn config
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── index.css
        ├── lib/
        │   ├── api.ts
        │   └── utils.ts                  # cn() for shadcn
        └── components/
            └── ui/
                └── button.tsx            # one shadcn component, proves the pipeline
```

**Per-file responsibilities:**

- `backend/app/main.py` — FastAPI app factory, includes routers, configures CORS.
- `backend/app/config.py` — Single `Settings` class (env-driven). No magic.
- `backend/app/db/base.py` — `DeclarativeBase` only. Models import from here.
- `backend/app/db/session.py` — SQLAlchemy engine + session factory + `get_db()` dependency.
- `backend/app/db/models.py` — All ten spine ORM models in one file. Splitting comes later if it grows.
- `backend/app/api/health.py` — Health-check router only.
- `backend/tests/conftest.py` — Pytest fixtures: in-memory SQLite engine, `TestClient`, DB-session fixture.
- `frontend/src/lib/api.ts` — Single fetch wrapper. Owns the `VITE_API_URL` env var.
- `frontend/src/App.tsx` — Renders a one-screen "health check" page proving frontend ↔ backend round-trip works.

---

## Task 1: Initialize repository structure and root tooling

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `package.json` (root)

- [ ] **Step 1: Verify you're inside the `what-should-i-play/` directory**

Run: `pwd` (or `cd` on Windows).
Expected: path ends with `what-should-i-play`.

- [ ] **Step 2: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.db
*.db-journal

# Node
node_modules/
dist/
.vite/

# Env
.env
.env.local

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 3: Create root `package.json`**

```json
{
  "name": "what-should-i-play",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "concurrently -n backend,frontend -c blue,magenta \"npm:dev:backend\" \"npm:dev:frontend\"",
    "dev:backend": "cd backend && uvicorn app.main:app --reload --port 8000",
    "dev:frontend": "cd frontend && npm run dev",
    "test": "cd backend && pytest",
    "lint": "cd backend && ruff check .",
    "build": "cd frontend && npm run build"
  },
  "devDependencies": {
    "concurrently": "^8.2.2"
  }
}
```

- [ ] **Step 4: Create `README.md`**

````markdown
# What Should I Play?

Local single-user game-recommendation web app. See `docs/superpowers/specs/2026-05-15-what-should-i-play-design.md` for the design.

## Prerequisites

- Python 3.11+
- Node 20+

## Setup

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/activate    # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e ".[dev]"
alembic upgrade head

# frontend
cd ../frontend
npm install

# root orchestration
cd ..
npm install
```

## Run

```bash
npm run dev          # runs backend + frontend together
npm run test         # backend tests
npm run lint         # ruff + eslint
npm run build        # frontend production build
```

Backend listens on `http://localhost:8000`. Frontend on `http://localhost:5173`.
````

- [ ] **Step 5: Initialize git and commit**

```bash
git init -b main          # skip if already initialized
git add .gitignore README.md package.json
git commit -m "chore: initialize repo structure and root scripts"
```

---

## Task 2: Backend Python package skeleton and tooling

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "wsip-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "python-dotenv>=1.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "mypy>=1.9",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true
```

- [ ] **Step 2: Create empty `backend/app/__init__.py` and `backend/tests/__init__.py`**

Both files have no content; they just mark the packages.

- [ ] **Step 3: Create `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "What Should I Play?"
    database_url: str = "sqlite:///./wsip.db"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
```

- [ ] **Step 4: Create the virtualenv and install in editable mode**

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate     # or: source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: `pip` reports successful install of FastAPI, SQLAlchemy, Alembic, pytest, ruff, mypy.

- [ ] **Step 5: Verify ruff runs**

Run: `ruff check .`
Expected: `All checks passed!` (or no output).

- [ ] **Step 6: Commit**

```bash
cd ..
git add backend/pyproject.toml backend/app/__init__.py backend/app/config.py backend/tests/__init__.py
git commit -m "feat(backend): scaffold Python package with FastAPI + ruff + pytest"
```

---

## Task 3: FastAPI app with health endpoint (TDD)

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/health.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write the failing test in `backend/tests/test_health.py`**

```python
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Add the `client` fixture in `backend/tests/conftest.py`**

```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 3: Run the test to confirm it fails**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: ImportError on `app.main` or `create_app` not defined.

- [ ] **Step 4: Create the empty router package `backend/app/api/__init__.py`**

File is empty.

- [ ] **Step 5: Create `backend/app/api/health.py`**

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Create `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
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
    return app


app = create_app()
```

- [ ] **Step 7: Run the test to confirm it passes**

Run: `pytest tests/test_health.py -v`
Expected: `1 passed`.

- [ ] **Step 8: Commit**

```bash
cd ..
git add backend/app/main.py backend/app/api/__init__.py backend/app/api/health.py backend/tests/conftest.py backend/tests/test_health.py
git commit -m "feat(backend): add FastAPI app factory and /api/health"
```

---

## Task 4: SQLAlchemy base, engine, and session

**Files:**
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/session.py`

- [ ] **Step 1: Create empty `backend/app/db/__init__.py`**

File is empty.

- [ ] **Step 2: Create `backend/app/db/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass
```

- [ ] **Step 3: Create `backend/app/db/session.py`**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# SQLite needs check_same_thread=False to play well with FastAPI's thread pool.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/
git commit -m "feat(backend): add SQLAlchemy declarative base and session factory"
```

---

## Task 5: ORM models for the stable-spine tables

This task creates **all ten spine tables** in one file. Subsystem-specific tables (`quiz_sessions`, `model_runs`, `play_sessions`) ship with their own sub-plans.

**Files:**
- Create: `backend/app/db/models.py`

- [ ] **Step 1: Create `backend/app/db/models.py`**

```python
"""Stable-spine ORM models for What Should I Play.

Subsystem-specific tables (quiz_sessions, model_runs, play_sessions) live in
their own sub-plans and are added later via Alembic migrations.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    igdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    steam_appid: Mapped[int | None] = mapped_column(
        Integer, unique=True, index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    store_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    critic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    steam_review_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    steam_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tags: Mapped[list[GameTag]] = relationship(back_populates="game", cascade="all, delete-orphan")
    embeddings: Mapped[list[GameEmbedding]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class GameEmbedding(Base):
    __tablename__ = "game_embeddings"
    __table_args__ = (UniqueConstraint("game_id", "model_name", name="uq_game_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    game: Mapped[Game] = relationship(back_populates="embeddings")


class GameTag(Base):
    __tablename__ = "game_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tag: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    # kind ∈ {"genre", "theme", "mechanic", "mood"}

    game: Mapped[Game] = relationship(back_populates="tags")


# ---------------------------------------------------------------------------
# User data
# ---------------------------------------------------------------------------


class LibraryEntry(Base):
    __tablename__ = "library_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "steam" | "manual"
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hours_played: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserGameState(Base):
    __tablename__ = "user_game_state"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # status ∈ {backlog, installed, currently_playing, completed, abandoned,
    #          wishlisted, hidden, not_interested, want_to_replay,
    #          multiplayer_only, tried_and_refunded}
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    enjoyment: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5
    finished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Preferences(Base):
    """Singleton row; we always read/write id=1."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    liked_genres: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    disliked_genres: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    liked_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    session_length_pref: Mapped[str] = mapped_column(String(16), default="any", nullable=False)
    difficulty_pref: Mapped[str] = mapped_column(String(16), default="any", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True, nullable=False
    )
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    # surface ∈ {quiz_result, for_you, library_browse}
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filters_applied: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abstention_path: Mapped[str] = mapped_column(String(16), nullable=False)
    # abstention_path ∈ {heuristic, ridge, lgbm}
    cluster_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    explanation_variant: Mapped[str] = mapped_column(String(16), nullable=False)
    # explanation_variant ∈ {templated, llm}

    shown_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_playing_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismiss_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # dismiss_reason ∈ {too_long, wrong_genre, too_expensive, wrong_platform,
    #                   already_played_elsewhere, not_interested}


class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "steam" | "igdb"
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "ok"|"partial"|"failed"
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class LLMCache(Base):
    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Verify ruff is happy**

Run: `cd backend && ruff check app/db/models.py`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd ..
git add backend/app/db/models.py
git commit -m "feat(backend): add ORM models for stable schema spine"
```

---

## Task 6: Alembic initialization and first migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_spine.py`

- [ ] **Step 1: Initialize Alembic in the backend directory**

```bash
cd backend
alembic init alembic
```

This creates `alembic/`, `alembic.ini`, and an empty `versions/` folder. Some files (notably `env.py`) need to be rewritten next.

- [ ] **Step 2: Replace `backend/alembic.ini` with this minimal version**

Open `backend/alembic.ini` and replace its entire contents with:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

(The empty `sqlalchemy.url` is intentional; `env.py` reads it from `Settings` instead.)

- [ ] **Step 3: Replace `backend/alembic/env.py` with this version**

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db.base import Base
from app.db import models  # noqa: F401 — imported for metadata side-effects

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Auto-generate the spine migration**

```bash
alembic revision --autogenerate -m "spine"
```

Expected: a new file like `alembic/versions/<hash>_spine.py` is created. Rename it to `0001_spine.py` for predictable ordering.

```bash
mv alembic/versions/*_spine.py alembic/versions/0001_spine.py
```

On Windows PowerShell: `mv` works the same, or use `Rename-Item`.

- [ ] **Step 5: Open `alembic/versions/0001_spine.py` and verify it contains `op.create_table` calls for every spine table**

Spot-check the file. You should see, in some order, create_table calls for: `games`, `game_embeddings`, `game_tags`, `library_entries`, `user_game_state`, `ratings`, `preferences`, `recommendation_events`, `data_sync_runs`, `llm_cache`.

If any table is missing, your `models.py` import in `env.py` is wrong — fix and re-run `alembic revision --autogenerate`.

- [ ] **Step 6: Apply the migration to a local dev DB**

```bash
alembic upgrade head
```

Expected: creates `wsip.db` in `backend/`, no errors.

- [ ] **Step 7: Verify the tables exist**

```bash
python -c "import sqlite3; print(sorted(r[0] for r in sqlite3.connect('wsip.db').execute('SELECT name FROM sqlite_master WHERE type=\"table\"')))"
```

Expected output should include all ten spine tables plus `alembic_version`.

- [ ] **Step 8: Commit**

```bash
cd ..
git add backend/alembic.ini backend/alembic/env.py backend/alembic/script.py.mako backend/alembic/versions/0001_spine.py
git commit -m "feat(backend): add Alembic and initial spine migration"
```

(Do NOT commit `wsip.db` — it's gitignored.)

---

## Task 7: Smoke tests for ORM models

These tests prove (a) every model can be inserted into an in-memory SQLite database, (b) unique constraints behave as designed, and (c) the conftest fixture wires Alembic correctly so future tests don't need to think about schema.

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Update `backend/tests/conftest.py` to add a `db_session` fixture**

Replace the entire contents of `backend/tests/conftest.py` with:

```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db import models  # noqa: F401 — register models with metadata
from app.main import create_app


@pytest.fixture
def db_engine():
    """Fresh in-memory SQLite database per test, schema created from metadata."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Iterator[Session]:
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 2: Write the failing tests in `backend/tests/test_models.py`**

```python
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    DataSyncRun,
    Game,
    GameEmbedding,
    GameTag,
    LibraryEntry,
    LLMCache,
    Preferences,
    Rating,
    RecommendationEvent,
    UserGameState,
)


def _make_game(session: Session, name: str = "Hollow Knight", slug: str = "hollow-knight") -> Game:
    game = Game(name=name, slug=slug)
    session.add(game)
    session.commit()
    return game


def test_game_can_be_created(db_session: Session) -> None:
    game = _make_game(db_session)
    assert game.id is not None
    assert game.created_at is not None


def test_game_slug_is_unique(db_session: Session) -> None:
    _make_game(db_session)
    with pytest.raises(IntegrityError):
        _make_game(db_session, name="Another", slug="hollow-knight")


def test_library_entry_one_per_game(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(LibraryEntry(game_id=game.id, source="steam", hours_played=12.5))
    db_session.commit()
    db_session.add(LibraryEntry(game_id=game.id, source="manual"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_rating_round_trips(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(Rating(game_id=game.id, enjoyment=5, finished=True, notes="loved it"))
    db_session.commit()
    row = db_session.query(Rating).filter_by(game_id=game.id).one()
    assert row.enjoyment == 5
    assert row.finished is True
    assert row.notes == "loved it"


def test_preferences_singleton_pattern(db_session: Session) -> None:
    db_session.add(
        Preferences(id=1, liked_genres=["rpg", "puzzle"], disliked_genres=["horror"])
    )
    db_session.commit()
    p = db_session.get(Preferences, 1)
    assert p is not None
    assert p.liked_genres == ["rpg", "puzzle"]
    assert p.disliked_genres == ["horror"]


def test_game_embedding_unique_per_model(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(
        GameEmbedding(game_id=game.id, model_name="all-MiniLM-L6-v2", dim=384, embedding=b"\x00" * 8)
    )
    db_session.commit()
    db_session.add(
        GameEmbedding(game_id=game.id, model_name="all-MiniLM-L6-v2", dim=384, embedding=b"\x01" * 8)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_recommendation_event_writes(db_session: Session) -> None:
    game = _make_game(db_session)
    db_session.add(
        RecommendationEvent(
            game_id=game.id,
            surface="for_you",
            rank=1,
            score=0.87,
            reason_codes=["HIGH_CRITIC_SCORE", "MATCHES_LIKED_GENRE:rpg"],
            model_version="heuristic-v0",
            feature_hash="abc123",
            filters_applied={"price_cap": 30},
            abstention_path="heuristic",
            explanation_variant="templated",
        )
    )
    db_session.commit()
    row = db_session.query(RecommendationEvent).one()
    assert row.reason_codes == ["HIGH_CRITIC_SCORE", "MATCHES_LIKED_GENRE:rpg"]
    assert row.filters_applied == {"price_cap": 30}


def test_remaining_spine_tables_accept_writes(db_session: Session) -> None:
    """Smoke test for the tables not covered above."""
    game = _make_game(db_session)
    db_session.add(GameTag(game_id=game.id, tag="metroidvania", kind="genre"))
    db_session.add(UserGameState(game_id=game.id, status="backlog"))
    db_session.add(
        DataSyncRun(source="steam", status="ok", counts={"added": 12}, finished_at=datetime.utcnow())
    )
    db_session.add(LLMCache(prompt_hash="deadbeef", response_json={"text": "hi"}))
    db_session.commit()

    assert db_session.query(GameTag).count() == 1
    assert db_session.query(UserGameState).count() == 1
    assert db_session.query(DataSyncRun).count() == 1
    assert db_session.query(LLMCache).count() == 1
```

- [ ] **Step 3: Run the model tests**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: 8 passed.

- [ ] **Step 4: Run the full test suite to make sure nothing else regressed**

Run: `pytest -v`
Expected: 9 passed (8 model + 1 health).

- [ ] **Step 5: Commit**

```bash
cd ..
git add backend/tests/conftest.py backend/tests/test_models.py
git commit -m "test(backend): add smoke tests for all spine ORM models"
```

---

## Task 8: Frontend Vite + React + TypeScript scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "wsip-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.4.5",
    "vite": "^5.3.1"
  }
}
```

- [ ] **Step 2: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: Create `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create `frontend/vite.config.ts`**

```ts
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
  },
});
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>What Should I Play?</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 7: Create a stub `frontend/src/App.tsx` (will be replaced in Task 10)**

```tsx
export default function App() {
  return <div>What Should I Play?</div>;
}
```

- [ ] **Step 8: Install frontend dependencies and verify dev server starts**

```bash
cd frontend
npm install
npm run dev
```

Expected: Vite reports `Local: http://localhost:5173/`. Open it in a browser and confirm "What Should I Play?" renders. Then Ctrl+C.

- [ ] **Step 9: Commit**

```bash
cd ..
git add frontend/package.json frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/index.html frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat(frontend): scaffold Vite + React + TypeScript app"
```

---

## Task 9: Tailwind CSS and shadcn/ui setup

**Files:**
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/index.css`
- Create: `frontend/components.json`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/components/ui/button.tsx`

- [ ] **Step 1: Install Tailwind, PostCSS, and shadcn/ui dependencies**

```bash
cd frontend
npm install -D tailwindcss postcss autoprefixer
npm install class-variance-authority clsx tailwind-merge lucide-react @radix-ui/react-slot
```

- [ ] **Step 2: Create `frontend/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 3: Create `frontend/postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 4: Create `frontend/src/index.css` (Tailwind base + design tokens)**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222 47% 11%;
    --primary: 222 47% 11%;
    --primary-foreground: 0 0% 98%;
    --muted: 210 40% 96%;
    --muted-foreground: 215 16% 47%;
    --border: 214 32% 91%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222 47% 11%;
    --foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 222 47% 11%;
    --muted: 217 33% 17%;
    --muted-foreground: 215 20% 65%;
    --border: 217 33% 17%;
  }

  body {
    @apply bg-background text-foreground;
    font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
  }
}
```

- [ ] **Step 5: Create `frontend/components.json` (shadcn manifest)**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.js",
    "css": "src/index.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils"
  }
}
```

- [ ] **Step 6: Create `frontend/src/lib/utils.ts`**

```ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 7: Create `frontend/src/components/ui/button.tsx` (standard shadcn Button)**

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-border bg-background hover:bg-muted",
        ghost: "hover:bg-muted",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";
```

- [ ] **Step 8: Verify the dev server still builds**

```bash
npm run dev
```

Open `http://localhost:5173`. The page still says "What Should I Play?" but now in Tailwind-styled body text. Ctrl+C.

- [ ] **Step 9: Commit**

```bash
cd ..
git add frontend/tailwind.config.js frontend/postcss.config.js frontend/src/index.css frontend/components.json frontend/src/lib/utils.ts frontend/src/components/ui/button.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): wire Tailwind + shadcn/ui foundation"
```

---

## Task 10: API client and end-to-end "health" page

This task proves the frontend can call the backend across the dev-server boundary.

**Files:**
- Create: `frontend/.env`
- Create: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/.env`**

```
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 2: Create `frontend/src/lib/api.ts`**

```ts
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export interface HealthResponse {
  status: string;
}
```

- [ ] **Step 3: Replace `frontend/src/App.tsx`**

```tsx
import { useEffect, useState } from "react";
import { apiGet, type HealthResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";

type State =
  | { kind: "loading" }
  | { kind: "ok"; status: string }
  | { kind: "error"; message: string };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const check = () => {
    setState({ kind: "loading" });
    apiGet<HealthResponse>("/api/health")
      .then((data) => setState({ kind: "ok", status: data.status }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  };

  useEffect(check, []);

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-md w-full space-y-4 text-center">
        <h1 className="text-3xl font-semibold">What Should I Play?</h1>
        <p className="text-muted-foreground">Foundation health check.</p>
        <div className="rounded-md border border-border p-4">
          {state.kind === "loading" && <p>Checking backend…</p>}
          {state.kind === "ok" && (
            <p className="text-green-600">Backend reachable. Status: {state.status}</p>
          )}
          {state.kind === "error" && (
            <p className="text-red-600">Backend unreachable: {state.message}</p>
          )}
        </div>
        <Button onClick={check} variant="outline">
          Re-check
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Start both servers and verify the round-trip**

In two terminals (or via `npm run dev` from repo root once `concurrently` is installed):

```bash
# terminal 1
cd backend && uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5173`. Expected: green "Backend reachable. Status: ok". If you see the red error message, check the browser console for CORS — Task 3 already configured `http://localhost:5173` as an allowed origin.

- [ ] **Step 5: Install root `concurrently` and verify `npm run dev`**

```bash
cd ..   # to repo root
npm install
npm run dev
```

Expected: both backend and frontend start with prefixed logs. Same green-status page at `localhost:5173`.

- [ ] **Step 6: Commit**

```bash
git add frontend/.env frontend/src/lib/api.ts frontend/src/App.tsx package-lock.json
git commit -m "feat: end-to-end health check, frontend talks to backend"
```

(Note: `frontend/.env` IS committed here because it only contains the dev URL — no secrets. Production overrides go in `.env.local`, which is gitignored.)

---

## Task 11: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Lint
        run: ruff check .
      - name: Test
        run: pytest -v

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - name: Install
        run: npm ci
      - name: Build
        run: npm run build
```

(No ESLint config exists yet, so `npm run lint` is intentionally omitted from CI; it can be added in a later sub-plan when the lint config lands. Build catches type errors via `tsc -b`, which is the meaningful check at this stage.)

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint + test backend, build frontend on push and PR"
```

- [ ] **Step 3: Push and verify (optional — only if a remote is configured)**

```bash
git push -u origin main
```

Expected: GitHub Actions runs both jobs and they both pass green. If you don't have a remote yet, skip this and verify locally:

```bash
cd backend && ruff check . && pytest -v && cd ..
cd frontend && npm run build && cd ..
```

Both should succeed.

---

## Task 12: README pass for completeness

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the entire contents of `README.md` with the final version**

````markdown
# What Should I Play?

Local single-user game-recommendation web app. Imports your Steam library, lets you add games manually, captures ratings, and runs a hybrid recommendation pipeline (content embeddings + heuristic priors + a personal reranker) that surfaces both games you already own and new games to buy. Includes a mood quiz and grounded LLM explanations.

See `docs/superpowers/specs/2026-05-15-what-should-i-play-design.md` for the full design.

## Status

Foundation sub-plan complete. Schema spine in place. End-to-end frontend ↔ backend health check working. Subsequent sub-plans add: library import, ratings, recommendations, mood quiz, eval harness, LLM features.

## Prerequisites

- Python 3.11+
- Node 20+

## Setup

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/activate         # Windows
# source .venv/bin/activate    # macOS/Linux
pip install -e ".[dev]"
alembic upgrade head

# frontend
cd ../frontend
npm install

# root orchestration
cd ..
npm install
```

## Daily commands

| Command | What it does |
|---|---|
| `npm run dev` | Runs backend (port 8000) and frontend (port 5173) together |
| `npm run test` | Runs backend pytest suite |
| `npm run lint` | Runs ruff on backend |
| `npm run build` | Production build of the frontend |

## Project layout

```
backend/    FastAPI + SQLAlchemy + Alembic
frontend/   React + Vite + Tailwind + shadcn/ui
docs/       Design specs and implementation plans
```

## Database

SQLite, file at `backend/wsip.db`. Schema managed by Alembic; migrations in `backend/alembic/versions/`. To reset the DB:

```bash
cd backend
rm wsip.db
alembic upgrade head
```
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: flesh out README with setup, commands, layout"
```

---

## Acceptance Criteria

When this plan is complete, all of the following must hold:

- `npm run dev` from the repo root starts the backend on `:8000` and the frontend on `:5173`.
- Opening `http://localhost:5173` shows a green "Backend reachable. Status: ok" message.
- `npm run test` runs 9 backend tests and they all pass.
- `npm run lint` produces no output (ruff clean).
- `npm run build` produces a `frontend/dist/` directory with no TypeScript errors.
- `backend/wsip.db` contains all ten spine tables plus `alembic_version`.
- `alembic downgrade base && alembic upgrade head` round-trips cleanly.
- `git log --oneline` shows ~12 commits, each scoped to one task.

---

## What this plan does NOT do

These are intentionally deferred to later sub-plans. Don't slip them in:

- Any business-logic endpoints (library, ratings, recommendations, quiz) — Sub-plan 2+
- Steam or IGDB clients — Sub-plan 2
- Embeddings or ML code — Sub-plan 4
- `recommendation_events` writes (the table exists; no code writes to it yet) — Sub-plan 3
- Authentication, multi-user logic — out of scope for v1
- Logging configuration beyond defaults — comes with the services that need it
- Subsystem tables: `quiz_sessions`, `model_runs`, `play_sessions` — ship with their respective sub-plans
- ESLint config — comes with the first real frontend feature

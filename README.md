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

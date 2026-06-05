# What Should I Play?

Local single-user game-recommendation web app. Imports your Steam library, lets you add games manually, captures ratings, and runs a hybrid recommendation pipeline (content embeddings + heuristic priors + a personal reranker) that surfaces both games you already own and new games to buy. Includes a mood quiz and grounded LLM explanations.

See `docs/superpowers/specs/2026-05-15-what-should-i-play-design.md` for the full design.

## Status

Foundation + library-import backend + **library page & ratings UI (2b)** + **onboarding, first-run & Steam-failure UX (2c)** complete. The React app has a router with three surfaces:

- **Onboarding** (`/onboarding`) — a first-run wizard (Welcome → Connect Steam → Preferences). A new user is auto-redirected here; finishing or skipping sets a persisted flag. This is now the first place the Steam import is triggered from the UI (no curl needed). Import failures show distinct, actionable guidance (private profile, invalid ID with inline re-entry, rate-limited, server API-key problem) with Retry / Skip import.
- **Library** (`/`) — responsive cover grid with a quick-rate side panel: rate each game Loved/Liked/Meh/Disliked/Hated (→ 5/4/3/2/1), set a play status, filter to rated-only, and sort. Optimistic with rollback. Shows a first-time empty state with an "Import from Steam" CTA when the library is empty.
- **Preferences** (`/preferences`) — liked/disliked genres, enjoyed types, session length, difficulty, plus a "Re-run setup" button.

Steam library imports via `POST /api/library/sync/steam` (the response now carries a machine-readable `error_code` on failure). Endpoints: `GET /api/library` (includes each game's rating + status), `POST /api/library/games/{id}/rating` (null clears), `PUT /api/library/games/{id}/status` (null clears), `GET|PUT /api/preferences`, `GET|PUT /api/onboarding`.

Manual game entry, a "For You" surface, and the mood quiz ship in later sub-plans.

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

## API Keys (required for library import)

Copy `backend/.env.example` to `backend/.env` and fill in the four values:

| Variable | Where to get it | Notes |
|---|---|---|
| `STEAM_API_KEY` | https://steamcommunity.com/dev/apikey | Use `localhost` for the domain field. |
| `STEAM_USER_ID` | Your numeric Steam ID (17 digits). Find via https://steamid.io if needed. | NOT your nickname. |
| `IGDB_CLIENT_ID` | https://dev.twitch.tv/console — register an app, "Confidential" client type. | |
| `IGDB_CLIENT_SECRET` | Same Twitch app — click "New Secret". | Treat like a password. |

`backend/.env` is gitignored. Do not commit it.

Once keys are set, trigger an import:

```bash
npm run dev
# in another terminal:
curl.exe -X POST http://localhost:8000/api/library/sync/steam -H "Content-Type: application/json" -d "{}"
```

Profile must be public (Steam → Edit Profile → Privacy Settings → Game Details = Public). Re-running the sync updates rather than duplicates.

## Daily commands

| Command | What it does |
|---|---|
| `npm run dev` | Runs backend (port 8000) and frontend (port 5173) together |
| `npm run test` | Runs backend pytest suite |
| `npm run lint` | Runs ruff on backend |
| `npm run build` | Production build of the frontend |
| `cd frontend && npm run test` | Runs the frontend Vitest suite (rating/status mapping) |

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

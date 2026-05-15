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

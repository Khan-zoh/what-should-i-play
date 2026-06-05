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

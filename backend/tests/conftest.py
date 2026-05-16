from collections.abc import Iterator

import pytest
import respx as _respx_module
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import models  # noqa: F401 — register models with metadata
from app.db.base import Base
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


@pytest.fixture
def respx_mock():
    """Yields a respx router that intercepts all httpx requests during the test."""
    with _respx_module.mock(assert_all_called=False) as router:
        yield router

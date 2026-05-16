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
    repo.upsert(
        igdb_id=12345, steam_appid=367520, name="Hollow Knight", slug="hollow-knight"
    )
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
    g2 = g_repo.upsert(
        igdb_id=2, steam_appid=20, name="Not In Library", slug="not-in-library"
    )
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

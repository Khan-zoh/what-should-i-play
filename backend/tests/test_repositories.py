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


# ---------------------------------------------------------------------------
# RatingRepository
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# UserGameStateRepository
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PreferencesRepository
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# LibraryEntryRepository.list_with_user_data
# ---------------------------------------------------------------------------


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


def test_preferences_defaults_onboarding_incomplete(db_session) -> None:
    from app.db.repositories import PreferencesRepository

    prefs = PreferencesRepository(db_session).get_or_create()
    db_session.commit()
    assert prefs.onboarding_completed is False


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

import pytest
from sqlalchemy.orm import Session

from app.db.models import DataSyncRun, Game, LibraryEntry
from app.db.repositories import (
    GameRepository,
    GameTagRepository,
    LibraryEntryRepository,
    SyncRunRepository,
)
from app.services.igdb_client import IgdbGame
from app.services.library_sync import LibrarySyncService, SyncOutcome
from app.services.steam_client import (
    InvalidSteamIdError,
    PrivateProfileError,
    SteamAuthError,
    SteamClientError,
    SteamGame,
    SteamLibraryResult,
    SteamRateLimitError,
)

# --- Test doubles --------------------------------------------------------


class FakeSteamClient:
    def __init__(self, result=None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc

    def get_owned_games(self, steam_id: str) -> SteamLibraryResult:
        if self._exc is not None:
            raise self._exc
        return self._result


class FakeIgdbClient:
    """Maps Steam appid -> (igdb_id, IgdbGame). None igdb_id => not found."""

    def __init__(
        self, mapping: dict[int, tuple[int | None, IgdbGame | None]]
    ) -> None:
        self._mapping = mapping

    def lookup_by_steam_appid(self, steam_appid: int) -> int | None:
        return self._mapping.get(steam_appid, (None, None))[0]

    def get_game(self, igdb_id: int) -> IgdbGame | None:
        for _, (mapped_id, igdb_game) in self._mapping.items():
            if mapped_id == igdb_id:
                return igdb_game
        return None


def _make_service(
    db_session: Session,
    steam: FakeSteamClient,
    igdb: FakeIgdbClient,
) -> LibrarySyncService:
    return LibrarySyncService(
        steam_client=steam,
        igdb_client=igdb,
        games=GameRepository(db_session),
        library=LibraryEntryRepository(db_session),
        sync_runs=SyncRunRepository(db_session),
        game_tags=GameTagRepository(db_session),
        session=db_session,
    )


# --- Tests ---------------------------------------------------------------


def test_successful_sync_creates_games_library_and_run(db_session: Session) -> None:
    steam = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=2,
            games=[
                SteamGame(
                    appid=220,
                    name="Half-Life 2",
                    playtime_minutes=600,
                    icon_hash="a",
                ),
                SteamGame(
                    appid=367520,
                    name="Hollow Knight",
                    playtime_minutes=4500,
                    icon_hash="b",
                ),
            ],
        )
    )
    igdb = FakeIgdbClient(
        {
            220: (
                100,
                IgdbGame(
                    igdb_id=100,
                    name="Half-Life 2",
                    slug="half-life-2",
                    critic_score=96.0,
                ),
            ),
            367520: (
                200,
                IgdbGame(
                    igdb_id=200,
                    name="Hollow Knight",
                    slug="hollow-knight",
                    critic_score=91.5,
                    release_year=2017,
                ),
            ),
        }
    )

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "ok"
    assert outcome.counts["added"] == 2
    assert outcome.counts["updated"] == 0
    assert outcome.error is None

    assert db_session.query(Game).count() == 2
    assert db_session.query(LibraryEntry).count() == 2

    runs = db_session.query(DataSyncRun).all()
    assert len(runs) == 1
    assert runs[0].status == "ok"
    assert runs[0].finished_at is not None


def test_private_profile_marks_run_failed_with_no_writes(db_session: Session) -> None:
    steam = FakeSteamClient(exc=PrivateProfileError("profile is private"))
    igdb = FakeIgdbClient({})

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "failed"
    assert "private" in outcome.error.lower()
    assert db_session.query(Game).count() == 0
    assert db_session.query(LibraryEntry).count() == 0

    run = db_session.query(DataSyncRun).one()
    assert run.status == "failed"
    assert "private" in (run.error or "").lower()


def test_rate_limit_marks_run_failed(db_session: Session) -> None:
    steam = FakeSteamClient(exc=SteamRateLimitError("429"))
    igdb = FakeIgdbClient({})

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "failed"
    assert "rate" in outcome.error.lower() or "429" in outcome.error


def test_partial_when_some_igdb_lookups_fail(db_session: Session) -> None:
    steam = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=2,
            games=[
                SteamGame(
                    appid=220,
                    name="Half-Life 2",
                    playtime_minutes=600,
                    icon_hash="a",
                ),
                SteamGame(
                    appid=999999,
                    name="Obscure Indie",
                    playtime_minutes=10,
                    icon_hash="z",
                ),
            ],
        )
    )
    # Only 220 is found; 999999 has no IGDB mapping.
    igdb = FakeIgdbClient(
        {
            220: (
                100,
                IgdbGame(igdb_id=100, name="Half-Life 2", slug="half-life-2"),
            ),
            999999: (None, None),
        }
    )

    service = _make_service(db_session, steam, igdb)
    outcome = service.sync_steam(steam_id="76561198000000000")

    assert outcome.status == "partial"
    assert outcome.counts["added"] == 2
    assert outcome.counts["unmatched_igdb"] == 1
    matched = db_session.query(Game).filter(Game.steam_appid == 220).one()
    assert matched.igdb_id == 100
    unmatched = db_session.query(Game).filter(Game.steam_appid == 999999).one()
    assert unmatched.igdb_id is None
    assert unmatched.name == "Obscure Indie"


def test_rerun_updates_existing_library_entries(db_session: Session) -> None:
    steam_first = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=1,
            games=[
                SteamGame(
                    appid=220,
                    name="Half-Life 2",
                    playtime_minutes=600,
                    icon_hash="a",
                )
            ],
        )
    )
    igdb = FakeIgdbClient(
        {220: (100, IgdbGame(igdb_id=100, name="Half-Life 2", slug="half-life-2"))}
    )

    _make_service(db_session, steam_first, igdb).sync_steam(steam_id="x")

    # Second run with updated playtime.
    steam_second = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=1,
            games=[
                SteamGame(
                    appid=220,
                    name="Half-Life 2",
                    playtime_minutes=1200,
                    icon_hash="a",
                )
            ],
        )
    )
    outcome = _make_service(db_session, steam_second, igdb).sync_steam(steam_id="x")

    assert outcome.counts["added"] == 0
    assert outcome.counts["updated"] == 1

    entry = db_session.query(LibraryEntry).one()
    # 1200 minutes -> 20.0 hours
    assert entry.hours_played == pytest.approx(20.0)


def test_outcome_is_a_dataclass_with_expected_fields(db_session: Session) -> None:
    steam = FakeSteamClient(result=SteamLibraryResult(game_count=0, games=[]))
    igdb = FakeIgdbClient({})
    outcome = _make_service(db_session, steam, igdb).sync_steam(steam_id="x")

    assert isinstance(outcome, SyncOutcome)
    assert outcome.run_id > 0
    assert outcome.status in {"ok", "partial", "failed"}
    assert isinstance(outcome.counts, dict)


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


def test_sync_persists_igdb_genres_and_themes_as_tags(db_session) -> None:
    from app.db.repositories import GameTagRepository

    igdb_game = IgdbGame(
        igdb_id=555,
        name="Hollow Knight",
        slug="hollow-knight",
        genres=["Platform", "Adventure"],
        themes=["Fantasy"],
    )
    steam = FakeSteamClient(
        result=SteamLibraryResult(
            game_count=1,
            games=[
                SteamGame(appid=367520, name="Hollow Knight", playtime_minutes=600, icon_hash=None)
            ],
        )
    )
    igdb = FakeIgdbClient({367520: (555, igdb_game)})
    service = _make_service(db_session, steam, igdb)

    service.sync_steam(steam_id="76561198000000000")

    game = db_session.query(Game).filter_by(steam_appid=367520).one()
    tags = GameTagRepository(db_session)
    assert tags.genres_for(game.id) == {"Platform", "Adventure"}
    assert tags.tags_by_game([game.id])[game.id]["theme"] == {"Fantasy"}

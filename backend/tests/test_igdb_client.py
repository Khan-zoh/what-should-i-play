from datetime import datetime, timedelta

import httpx
import pytest

from app.services.igdb_client import IgdbAuth, IgdbAuthError, IgdbClient, IgdbGame

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def test_fetches_token_on_first_call(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).respond(
        200,
        json={"access_token": "tok_abc", "expires_in": 5400, "token_type": "bearer"},
    )

    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    token = auth.get_token()

    assert token == "tok_abc"


def test_caches_token_until_expiration(respx_mock) -> None:
    route = respx_mock.post(TWITCH_TOKEN_URL).respond(
        200,
        json={"access_token": "tok_abc", "expires_in": 5400, "token_type": "bearer"},
    )

    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    auth.get_token()
    auth.get_token()
    auth.get_token()

    assert route.call_count == 1


def test_refetches_after_expiration(respx_mock) -> None:
    route = respx_mock.post(TWITCH_TOKEN_URL).respond(
        200,
        json={"access_token": "tok_old", "expires_in": 5400, "token_type": "bearer"},
    )
    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    auth.get_token()

    # Force expiration by rewinding the cached expiration manually.
    auth._expires_at = datetime.utcnow() - timedelta(seconds=1)

    route.respond(
        200,
        json={"access_token": "tok_new", "expires_in": 5400, "token_type": "bearer"},
    )
    new_token = auth.get_token()
    assert new_token == "tok_new"
    assert route.call_count == 2


def test_bad_credentials_raise(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).respond(
        401, json={"status": 401, "message": "invalid client"}
    )

    auth = IgdbAuth(client_id="bad", client_secret="bad")
    with pytest.raises(IgdbAuthError):
        auth.get_token()


def test_token_request_sends_required_form_fields(respx_mock) -> None:
    route = respx_mock.post(TWITCH_TOKEN_URL).respond(
        200, json={"access_token": "tok", "expires_in": 5400, "token_type": "bearer"}
    )

    auth = IgdbAuth(client_id="my_id", client_secret="my_secret")
    auth.get_token()

    body = route.calls.last.request.content.decode()
    assert "client_id=my_id" in body
    assert "client_secret=my_secret" in body
    assert "grant_type=client_credentials" in body


def test_network_error_propagates(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).mock(side_effect=httpx.ConnectError("nope"))

    auth = IgdbAuth(client_id="cid", client_secret="csecret")
    with pytest.raises(httpx.ConnectError):
        auth.get_token()


IGDB_EXTERNAL = "https://api.igdb.com/v4/external_games"
IGDB_GAMES = "https://api.igdb.com/v4/games"


def _stub_token(respx_mock) -> None:
    respx_mock.post(TWITCH_TOKEN_URL).respond(
        200, json={"access_token": "tok", "expires_in": 5400, "token_type": "bearer"}
    )


def test_lookup_by_steam_appid_returns_igdb_id(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_EXTERNAL).respond(
        200, json=[{"id": 999, "uid": "367520", "external_game_source": 1, "game": 12345}]
    )

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    igdb_id = client.lookup_by_steam_appid(367520)
    assert igdb_id == 12345


def test_lookup_by_steam_appid_returns_none_when_not_found(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_EXTERNAL).respond(200, json=[])

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    assert client.lookup_by_steam_appid(99999999) is None


def test_get_game_returns_metadata(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_GAMES).respond(
        200,
        json=[
            {
                "id": 12345,
                "name": "Hollow Knight",
                "slug": "hollow-knight",
                "summary": "A 2D action adventure.",
                "cover": {"image_id": "co1rgi"},
                "genres": [{"name": "Platform"}, {"name": "Adventure"}],
                "themes": [{"name": "Fantasy"}],
                "first_release_date": 1488499200,  # 2017-03-03
                "total_rating": 91.5,
                "total_rating_count": 800,
                "url": "https://www.igdb.com/games/hollow-knight",
            }
        ],
    )

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    game = client.get_game(12345)

    assert isinstance(game, IgdbGame)
    assert game.igdb_id == 12345
    assert game.name == "Hollow Knight"
    assert game.slug == "hollow-knight"
    assert game.summary == "A 2D action adventure."
    assert game.release_year == 2017
    assert game.critic_score == 91.5
    assert (
        game.cover_url
        == "https://images.igdb.com/igdb/image/upload/t_cover_big/co1rgi.jpg"
    )
    assert "Platform" in game.genres
    assert "Adventure" in game.genres
    assert "Fantasy" in game.themes


def test_get_game_returns_none_when_not_found(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_GAMES).respond(200, json=[])

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    assert client.get_game(0) is None


def test_get_game_handles_missing_optional_fields(respx_mock) -> None:
    _stub_token(respx_mock)
    respx_mock.post(IGDB_GAMES).respond(
        200,
        json=[{"id": 1, "name": "Bare Minimum", "slug": "bare-minimum"}],
    )

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    game = client.get_game(1)

    assert game is not None
    assert game.name == "Bare Minimum"
    assert game.summary is None
    assert game.cover_url is None
    assert game.release_year is None
    assert game.critic_score is None
    assert game.genres == []
    assert game.themes == []


def test_request_includes_client_id_and_bearer(respx_mock) -> None:
    _stub_token(respx_mock)
    route = respx_mock.post(IGDB_EXTERNAL).respond(200, json=[])

    client = IgdbClient(IgdbAuth("cid", "csecret"), client_id="cid")
    client.lookup_by_steam_appid(220)

    headers = route.calls.last.request.headers
    assert headers["client-id"] == "cid"
    assert headers["authorization"] == "Bearer tok"

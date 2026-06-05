import httpx
import pytest

from app.services.steam_client import (
    InvalidSteamIdError,
    PrivateProfileError,
    SteamClient,
    SteamRateLimitError,
)

STEAM_BASE = "https://api.steampowered.com"
OWNED_GAMES_PATH = f"{STEAM_BASE}/IPlayerService/GetOwnedGames/v1/"


def test_get_owned_games_returns_parsed_games(respx_mock) -> None:
    respx_mock.get(OWNED_GAMES_PATH).respond(
        200,
        json={
            "response": {
                "game_count": 2,
                "games": [
                    {
                        "appid": 220,
                        "name": "Half-Life 2",
                        "playtime_forever": 1200,
                        "img_icon_url": "abc",
                    },
                    {
                        "appid": 367520,
                        "name": "Hollow Knight",
                        "playtime_forever": 4500,
                        "img_icon_url": "def",
                    },
                ],
            }
        },
    )

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    result = client.get_owned_games("76561198000000000")

    assert result.game_count == 2
    assert len(result.games) == 2
    assert result.games[0].appid == 220
    assert result.games[0].name == "Half-Life 2"
    assert result.games[0].playtime_minutes == 1200
    assert result.games[1].appid == 367520


def test_private_profile_raises(respx_mock) -> None:
    # Steam returns a 200 with empty response object when the profile is private.
    respx_mock.get(OWNED_GAMES_PATH).respond(200, json={"response": {}})

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(PrivateProfileError):
        client.get_owned_games("76561198000000000")


def test_invalid_steam_id_raises(respx_mock) -> None:
    # An invalid/non-numeric steamid yields HTTP 500 from Steam.
    respx_mock.get(OWNED_GAMES_PATH).respond(500, text="Internal Server Error")

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(InvalidSteamIdError):
        client.get_owned_games("not_a_real_id")


def test_rate_limit_raises(respx_mock) -> None:
    respx_mock.get(OWNED_GAMES_PATH).respond(429, text="Too Many Requests")

    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(SteamRateLimitError):
        client.get_owned_games("76561198000000000")


def test_query_includes_required_params(respx_mock) -> None:
    route = respx_mock.get(OWNED_GAMES_PATH).respond(
        200, json={"response": {"game_count": 0, "games": []}}
    )

    client = SteamClient(api_key="MY_KEY", timeout_seconds=5.0)
    client.get_owned_games("76561198000000000")

    request = route.calls.last.request
    assert request.url.params["key"] == "MY_KEY"
    assert request.url.params["steamid"] == "76561198000000000"
    assert request.url.params["format"] == "json"
    assert request.url.params["include_appinfo"] == "true"
    assert request.url.params["include_played_free_games"] == "true"


def test_auth_error_on_401(respx_mock) -> None:
    from app.services.steam_client import SteamAuthError

    respx_mock.get(OWNED_GAMES_PATH).respond(401, text="Unauthorized")
    client = SteamClient(api_key="bad", timeout_seconds=5.0)
    with pytest.raises(SteamAuthError):
        client.get_owned_games("76561198000000000")


def test_auth_error_on_403(respx_mock) -> None:
    from app.services.steam_client import SteamAuthError

    respx_mock.get(OWNED_GAMES_PATH).respond(403, text="Forbidden")
    client = SteamClient(api_key="bad", timeout_seconds=5.0)
    with pytest.raises(SteamAuthError):
        client.get_owned_games("76561198000000000")


def test_public_empty_library_is_success_not_private(respx_mock) -> None:
    # Public profile that owns zero games: response has game_count but no games key.
    respx_mock.get(OWNED_GAMES_PATH).respond(200, json={"response": {"game_count": 0}})
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    result = client.get_owned_games("76561198000000000")
    assert result.game_count == 0
    assert result.games == []


def test_truly_empty_response_still_private(respx_mock) -> None:
    respx_mock.get(OWNED_GAMES_PATH).respond(200, json={"response": {}})
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(PrivateProfileError):
        client.get_owned_games("76561198000000000")


def test_network_error_wrapped_as_steam_error(respx_mock) -> None:
    from app.services.steam_client import SteamClientError

    respx_mock.get(OWNED_GAMES_PATH).mock(side_effect=httpx.ConnectError("nope"))
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(SteamClientError):
        client.get_owned_games("76561198000000000")


def test_parse_error_is_not_swallowed(respx_mock) -> None:
    # A games entry missing 'appid' is a contract bug, not a Steam failure:
    # it must surface as KeyError, NOT be wrapped into SteamClientError.
    respx_mock.get(OWNED_GAMES_PATH).respond(
        200, json={"response": {"game_count": 1, "games": [{"name": "no appid"}]}}
    )
    client = SteamClient(api_key="test_key", timeout_seconds=5.0)
    with pytest.raises(KeyError):
        client.get_owned_games("76561198000000000")

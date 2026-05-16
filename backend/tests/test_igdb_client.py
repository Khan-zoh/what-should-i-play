from datetime import datetime, timedelta

import httpx
import pytest

from app.services.igdb_client import IgdbAuth, IgdbAuthError

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

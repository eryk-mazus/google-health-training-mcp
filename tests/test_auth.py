import os

import pytest

from pixel_health_mcp.auth import _fetch_token_from_loopback


class FakeFlow:
    def __init__(self, token_uri: str = "https://oauth2.googleapis.com/token") -> None:
        self.client_config = {"token_uri": token_uri}
        self.response: str | None = None
        self.override_during_exchange: str | None = None

    def fetch_token(self, *, authorization_response: str) -> None:
        self.response = authorization_response
        self.override_during_exchange = os.environ.get("OAUTHLIB_INSECURE_TRANSPORT")


def test_loopback_exchange_is_narrowly_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)
    flow = FakeFlow()

    _fetch_token_from_loopback(
        flow,
        authorization_response="http://127.0.0.1:8765/oauth/callback?code=example",
        callback_uri="http://127.0.0.1:8765/oauth/callback",
    )

    assert flow.response is not None
    assert flow.override_during_exchange == "1"
    assert "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ


def test_loopback_exchange_rejects_nonlocal_callback() -> None:
    with pytest.raises(RuntimeError, match="loopback"):
        _fetch_token_from_loopback(
            FakeFlow(),
            authorization_response="http://example.com/oauth/callback?code=example",
            callback_uri="http://example.com/oauth/callback",
        )


def test_loopback_exchange_rejects_non_google_token_endpoint() -> None:
    with pytest.raises(RuntimeError, match="token endpoint"):
        _fetch_token_from_loopback(
            FakeFlow("http://oauth2.googleapis.com/token"),
            authorization_response="http://127.0.0.1:8765/oauth/callback?code=example",
            callback_uri="http://127.0.0.1:8765/oauth/callback",
        )

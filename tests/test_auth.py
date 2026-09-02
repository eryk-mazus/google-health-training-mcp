import os

import pytest

import google_health_training_mcp.auth as auth_module
from google_health_training_mcp.auth import TokenStore, _fetch_token_from_loopback


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


def test_file_store_reads_legacy_path_and_writes_new_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current" / "google-oauth.json"
    legacy = tmp_path / "legacy" / "google-oauth.json"
    legacy.parent.mkdir()
    legacy.write_text('{"marker": "legacy"}\n', encoding="utf-8")
    legacy.chmod(0o600)
    monkeypatch.setattr(auth_module, "TOKEN_FILE", current)
    monkeypatch.setattr(auth_module, "LEGACY_TOKEN_FILE", legacy)

    store = TokenStore("file")
    assert store.load() == {"marker": "legacy"}

    store.save({"marker": "current"})
    assert current.exists()
    assert current.stat().st_mode & 0o777 == 0o600
    assert store.load() == {"marker": "current"}

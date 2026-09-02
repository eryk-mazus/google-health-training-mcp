import json

import pytest

import google_health_training_mcp.config as config_module
from google_health_training_mcp.config import Settings


def test_settings_load_legacy_config_and_save_under_current_name(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "GOOGLE_HEALTH_TRAINING_CLIENT_SECRETS",
        "GOOGLE_HEALTH_TRAINING_OAUTH_CALLBACK_PORT",
        "PIXEL_HEALTH_CLIENT_SECRETS",
        "PIXEL_HEALTH_OAUTH_CALLBACK_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    current = tmp_path / "current" / "config.json"
    legacy = tmp_path / "legacy" / "config.json"
    legacy.parent.mkdir()
    legacy.write_text(
        json.dumps(
            {
                "client_secrets_file": "/example/client.json",
                "credential_store": "file",
                "oauth_callback_port": 8765,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", current)
    monkeypatch.setattr(config_module, "LEGACY_CONFIG_PATH", legacy)

    settings = Settings.load()
    assert settings.client_secrets_file == "/example/client.json"
    assert settings.credential_store == "file"

    settings.save()
    assert current.exists()
    assert current.stat().st_mode & 0o777 == 0o600

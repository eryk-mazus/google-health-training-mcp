from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


CredentialStoreName = Literal["keyring", "file"]


def _config_root() -> Path:
    override = os.environ.get("PIXEL_HEALTH_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "pixel-health-mcp"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "pixel-health-mcp"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "pixel-health-mcp"


def _data_root() -> Path:
    override = os.environ.get("PIXEL_HEALTH_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "pixel-health-mcp"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "pixel-health-mcp"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "pixel-health-mcp"


CONFIG_PATH = _config_root() / "config.json"
TOKEN_FILE = _data_root() / "google-oauth.json"


@dataclass(slots=True)
class Settings:
    client_secrets_file: str | None = None
    credential_store: CredentialStoreName = "keyring"
    oauth_callback_port: int = 8765

    @property
    def callback_uri(self) -> str:
        return f"http://127.0.0.1:{self.oauth_callback_port}/oauth/callback"

    @classmethod
    def load(cls) -> "Settings":
        values: dict[str, object] = {}
        if CONFIG_PATH.exists():
            values = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

        env_secret = os.environ.get("PIXEL_HEALTH_CLIENT_SECRETS")
        if env_secret:
            values["client_secrets_file"] = env_secret
        env_port = os.environ.get("PIXEL_HEALTH_OAUTH_CALLBACK_PORT")
        if env_port:
            values["oauth_callback_port"] = int(env_port)

        settings = cls(**values)
        if settings.credential_store not in ("keyring", "file"):
            raise ValueError("credential_store must be 'keyring' or 'file'")
        if not 1024 <= settings.oauth_callback_port <= 65535:
            raise ValueError("oauth_callback_port must be between 1024 and 65535")
        return settings

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            CONFIG_PATH.chmod(0o600)

    def require_client_secrets(self) -> Path:
        if not self.client_secrets_file:
            raise RuntimeError(
                "Google OAuth client JSON is not configured. Run "
                "`pixel-health-mcp auth --client-secrets /path/to/client_secret.json`."
            )
        path = Path(self.client_secrets_file).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"Google OAuth client JSON does not exist: {path}")
        return path

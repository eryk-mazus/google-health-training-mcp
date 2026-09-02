from __future__ import annotations

import json
import os
import threading
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from keyring.errors import KeyringError

from google_health_training_mcp.config import LEGACY_TOKEN_FILE, TOKEN_FILE, Settings


SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]

KEYRING_SERVICE = "google-health-training-mcp"
LEGACY_KEYRING_SERVICE = "pixel-health-mcp"
KEYRING_ACCOUNT = "google-oauth-default"


class CredentialStoreError(RuntimeError):
    pass


class TokenStore:
    def __init__(self, mode: str):
        self.mode = mode

    def load(self) -> dict[str, object] | None:
        if self.mode == "keyring":
            try:
                value = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
                if not value:
                    value = keyring.get_password(LEGACY_KEYRING_SERVICE, KEYRING_ACCOUNT)
            except KeyringError as exc:
                raise CredentialStoreError(_keyring_help(exc)) from exc
            return json.loads(value) if value else None

        token_file = TOKEN_FILE if TOKEN_FILE.exists() else LEGACY_TOKEN_FILE
        if not token_file.exists():
            return None
        _check_private_file(token_file)
        return json.loads(token_file.read_text(encoding="utf-8"))

    def save(self, value: dict[str, object]) -> None:
        payload = json.dumps(value)
        if self.mode == "keyring":
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, payload)
            except KeyringError as exc:
                raise CredentialStoreError(_keyring_help(exc)) from exc
            return

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(TOKEN_FILE, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        if os.name != "nt":
            TOKEN_FILE.chmod(0o600)

    def delete(self) -> bool:
        if self.mode == "keyring":
            try:
                deleted = False
                for service in (KEYRING_SERVICE, LEGACY_KEYRING_SERVICE):
                    if keyring.get_password(service, KEYRING_ACCOUNT):
                        keyring.delete_password(service, KEYRING_ACCOUNT)
                        deleted = True
                return deleted
            except KeyringError as exc:
                raise CredentialStoreError(_keyring_help(exc)) from exc
        deleted = False
        for token_file in (TOKEN_FILE, LEGACY_TOKEN_FILE):
            if token_file.exists():
                token_file.unlink()
                deleted = True
        return deleted


def _keyring_help(exc: Exception) -> str:
    return (
        "No usable OS keyring is available. Install/configure a keyring backend, or explicitly "
        "use `google-health-training-mcp auth --credential-store file ...` to store the refresh token "
        f"in a permission-restricted local file. Original error: {exc}"
    )


def _check_private_file(path: Path) -> None:
    if os.name == "nt":
        return
    if path.stat().st_mode & 0o077:
        raise CredentialStoreError(
            f"Refusing to read credential file with group/other permissions: {path}. "
            f"Run `chmod 600 {path}`."
        )


def _credentials_to_dict(credentials: Credentials) -> dict[str, object]:
    return json.loads(credentials.to_json())


def _fetch_token_from_loopback(
    flow: Flow, *, authorization_response: str, callback_uri: str
) -> None:
    """Exchange a code received over a verified local HTTP callback.

    OAuthlib rejects every non-HTTPS authorization response unless its development
    override is enabled. Google explicitly permits HTTP for loopback redirect URIs,
    so enable the override only around parsing/exchanging this callback and only
    after checking that the callback is local and the token endpoint remains HTTPS.
    """
    callback = urlparse(callback_uri)
    if callback.scheme != "http" or callback.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("OAuth HTTP callback must use the local loopback interface")

    token_uri = str(flow.client_config.get("token_uri", ""))
    token_endpoint = urlparse(token_uri)
    if token_endpoint.scheme != "https" or token_endpoint.hostname != "oauth2.googleapis.com":
        raise RuntimeError("Refusing to exchange credentials with an unexpected token endpoint")

    environment_name = "OAUTHLIB_INSECURE_TRANSPORT"
    previous = os.environ.get(environment_name)
    os.environ[environment_name] = "1"
    try:
        flow.fetch_token(authorization_response=authorization_response)
    finally:
        if previous is None:
            os.environ.pop(environment_name, None)
        else:
            os.environ[environment_name] = previous


def load_credentials(settings: Settings, *, refresh: bool = True) -> Credentials:
    info = TokenStore(settings.credential_store).load()
    if not info:
        raise RuntimeError(
            "Google Health is not authenticated. Run `google-health-training-mcp auth` first."
        )
    credentials = Credentials.from_authorized_user_info(info, scopes=SCOPES)
    if refresh and (not credentials.valid or credentials.expired):
        if not credentials.refresh_token:
            raise RuntimeError("Stored Google credentials have no refresh token; authenticate again.")
        credentials.refresh(Request())
        TokenStore(settings.credential_store).save(_credentials_to_dict(credentials))
    return credentials


@dataclass(slots=True)
class OAuthResult:
    authorization_response: str | None = None
    error: str | None = None


def authenticate(settings: Settings, *, open_browser: bool = True, timeout_seconds: int = 300) -> None:
    client_file = settings.require_client_secrets()
    flow = Flow.from_client_secrets_file(
        str(client_file),
        scopes=SCOPES,
        redirect_uri=settings.callback_uri,
        autogenerate_code_verifier=True,
    )
    authorization_url, expected_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    result = OAuthResult()
    completed = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path != "/oauth/callback":
                self.send_response(404)
                self.end_headers()
                return
            if query.get("state", [None])[0] != expected_state:
                result.error = "OAuth state mismatch"
                status, message = 400, "Authorization failed: state mismatch."
            elif "error" in query:
                result.error = query["error"][0]
                status, message = 400, "Google authorization was denied. You may close this tab."
            elif "code" not in query:
                result.error = "OAuth callback did not include a code"
                status, message = 400, "Authorization failed: missing code."
            else:
                result.authorization_response = settings.callback_uri + "?" + parsed.query
                status, message = 200, "Google Health authorization complete. You may close this tab."

            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            completed.set()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", settings.oauth_callback_port), CallbackHandler)
    server.timeout = 1
    print("Open this URL in your browser and approve read-only Google Health access:\n")
    print(authorization_url)
    print(f"\nWaiting up to {timeout_seconds} seconds for {settings.callback_uri} ...")
    if open_browser:
        webbrowser.open(authorization_url)

    deadline = datetime.now(UTC).timestamp() + timeout_seconds
    while not completed.is_set() and datetime.now(UTC).timestamp() < deadline:
        server.handle_request()
    server.server_close()

    if not completed.is_set():
        raise TimeoutError("Timed out waiting for the Google OAuth callback.")
    if result.error:
        raise RuntimeError(result.error)
    if not result.authorization_response:
        raise RuntimeError("OAuth callback completed without an authorization response.")

    _fetch_token_from_loopback(
        flow,
        authorization_response=result.authorization_response,
        callback_uri=settings.callback_uri,
    )
    if not flow.credentials.refresh_token:
        raise RuntimeError(
            "Google did not return a refresh token. Revoke the app's prior access and authenticate again."
        )
    TokenStore(settings.credential_store).save(_credentials_to_dict(flow.credentials))


def authentication_status(settings: Settings, *, verify_online: bool = False) -> dict[str, object]:
    try:
        credentials = load_credentials(settings, refresh=verify_online)
    except Exception as exc:
        return {
            "authenticated": False,
            "credentialStore": settings.credential_store,
            "error": str(exc),
        }
    return {
        "authenticated": bool(credentials.valid or credentials.refresh_token),
        "onlineVerified": verify_online,
        "credentialStore": settings.credential_store,
        "hasRefreshToken": bool(credentials.refresh_token),
        "accessTokenValid": bool(credentials.valid),
        "expiresAt": credentials.expiry.isoformat() if credentials.expiry else None,
        "scopes": SCOPES,
    }

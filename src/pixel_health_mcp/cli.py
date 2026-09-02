from __future__ import annotations

import argparse
import json
from pathlib import Path

from pixel_health_mcp.auth import TokenStore, authenticate, authentication_status
from pixel_health_mcp.config import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pixel-health-mcp",
        description="Local, read-only MCP access to personal Google Health data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth = subparsers.add_parser("auth", help="Complete one-time Google OAuth authorization")
    auth.add_argument("--client-secrets", type=Path, help="Downloaded Google OAuth client JSON")
    auth.add_argument(
        "--credential-store",
        choices=("keyring", "file"),
        help="Use the OS keyring (recommended) or an explicit chmod-600 token file",
    )
    auth.add_argument("--no-browser", action="store_true", help="Print the URL without opening it")
    auth.add_argument("--timeout", type=int, default=300, help="OAuth callback timeout in seconds")

    status = subparsers.add_parser("auth-status", help="Show credential status without secrets")
    status.add_argument("--online", action="store_true", help="Refresh the token to verify access")

    subparsers.add_parser("serve", help="Run the local MCP server over STDIO")
    subparsers.add_parser("doctor", help="Check local configuration and credentials")
    subparsers.add_parser("logout", help="Delete locally stored Google OAuth credentials")
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = Settings.load()

    if args.command == "serve":
        from pixel_health_mcp.server import run

        run()
        return

    if args.command == "auth":
        if args.client_secrets:
            settings.client_secrets_file = str(args.client_secrets.expanduser().resolve())
        if args.credential_store:
            settings.credential_store = args.credential_store
        settings.save()
        authenticate(settings, open_browser=not args.no_browser, timeout_seconds=args.timeout)
        print("Google Health authorization saved successfully.")
        return

    if args.command == "auth-status":
        print(json.dumps(authentication_status(settings, verify_online=args.online), indent=2))
        return

    if args.command == "doctor":
        checks = {
            "clientSecretsConfigured": bool(settings.client_secrets_file),
            "clientSecretsExists": bool(
                settings.client_secrets_file
                and Path(settings.client_secrets_file).expanduser().is_file()
            ),
            "callbackUri": settings.callback_uri,
            "credentialStore": settings.credential_store,
            "authentication": authentication_status(settings, verify_online=False),
        }
        print(json.dumps(checks, indent=2))
        return

    if args.command == "logout":
        deleted = TokenStore(settings.credential_store).delete()
        print("Stored Google OAuth credentials deleted." if deleted else "No stored credentials found.")

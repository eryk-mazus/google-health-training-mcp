# Pixel Health MCP

Pixel Health MCP is a local, read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for personal training and recovery data in the Google Health API. It lets Codex and other MCP-compatible agents retrieve workouts recorded by devices such as Pixel Watch, inspect heart-rate data, and obtain a compact recovery snapshot.

The server uses STDIO: the MCP client starts it when needed and stops it with the client session. Google access is authorized once with OAuth, and the stored refresh token lets later sessions fetch current data without signing in every time.

This is an independent community project. It is not affiliated with or endorsed by Google, Fitbit, or OpenAI.

## Current tools

| Tool | Purpose |
| --- | --- |
| `health_auth_status` | Check whether credentials exist and optionally verify them online |
| `list_workouts` | List workout summaries for an inclusive date range |
| `get_workout` | Retrieve one workout, including metrics, events, laps, and splits |
| `get_workout_heart_rate` | Retrieve bounded, downsampled heart-rate telemetry and summary statistics |
| `get_recovery_snapshot` | Retrieve sleep and daily recovery-related source measurements |

The initial version deliberately excludes GPS routes and every Google Health write operation. It returns source measurements, not medical diagnoses or a proprietary readiness score.

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- A Google account with Google Health data
- A Google Cloud project with the Google Health API enabled
- An MCP client such as Codex

After cloning the repository, install the locked development environment from its root:

```bash
uv sync --extra dev
```

Use `uv run pixel-health-mcp ...` for the commands below. This keeps the instructions independent of the repository's location and does not require activating a virtual environment.

## Configure Google OAuth

In [Google Cloud Console](https://console.cloud.google.com/):

1. Create or select a project and enable **Google Health API**.
2. Configure the OAuth consent screen. While the app remains in Testing status, add the Google account containing your health data as a test user.
3. Add these scopes:
   - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
   - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
   - `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
4. Create an OAuth client of type **Web application**. The Google Health setup wizard asks for `https://www.google.com` as an authorized redirect URI; keep that entry.
5. Open that client's settings and add this second authorized redirect URI for Pixel Health MCP's automatic local callback:

   ```text
   http://127.0.0.1:8765/oauth/callback
   ```

6. Download the client JSON and keep it outside this repository.

Google's Health-specific wizard documents the `https://www.google.com` setup value. Pixel Health MCP additionally needs its own exact callback because OAuth redirects back to the application that initiated authorization. Google permits local HTTP redirect URIs for testing, including localhost IP addresses. The callback listens only on the loopback interface and exists only while the `auth` command is running. See Google's [Google Health API setup guide](https://developers.google.com/health/setup) and [web-server OAuth redirect requirements](https://developers.google.com/identity/protocols/oauth2/web-server#creatingcred).

Google documents that refresh tokens issued to an external OAuth app in Testing status [expire after seven days](https://developers.google.com/identity/protocols/oauth2#expiration). A personal development setup may therefore need periodic reauthorization until its consent configuration is suitable for long-term use.

## Authorize once

The OS keyring is the default and recommended credential store:

```bash
uv run pixel-health-mcp auth --client-secrets /absolute/path/to/client_secret.json
uv run pixel-health-mcp auth-status --online
```

The first command opens the Google consent page and waits for the local callback. The project stores the client JSON's path in the user's platform-specific configuration directory; it does not copy the file into the repository.

If the machine has no usable keyring backend, explicitly opt into a permission-restricted local token file:

```bash
uv run pixel-health-mcp auth \
  --credential-store file \
  --client-secrets /absolute/path/to/client_secret.json
```

On Linux, file mode defaults to `~/.local/share/pixel-health-mcp/google-oauth.json` with mode `0600`. The equivalent platform-specific user data directory is used on macOS and Windows. File mode is less isolated than an OS keyring, but the token remains outside the repository.

Useful checks:

```bash
uv run pixel-health-mcp doctor
uv run pixel-health-mcp auth-status --online
```

No command prints access or refresh token values.

## Add the server to Codex

Run the following with absolute paths so Codex can start the server regardless of its working directory:

```bash
codex mcp add pixel-health -- \
  /absolute/path/to/uv --directory /absolute/path/to/pixel-health-mcp \
  run pixel-health-mcp serve
```

`command -v uv` prints the first path. Run `pwd` from the repository root to obtain the second. Then verify the saved configuration:

```bash
codex mcp list
```

Restart Codex if it was already open. The configuration persists, but the Python process does not run continuously: Codex launches it when the MCP is enabled. Each data tool loads the stored credentials, refreshes the access token when required, and queries the Google Health API.

For another MCP client, configure a local STDIO server with the same command and arguments:

```text
/absolute/path/to/uv --directory /absolute/path/to/pixel-health-mcp run pixel-health-mcp serve
```

## Suggested agent workflow

An agent should begin with `health_auth_status`. It can then use `list_workouts` for a bounded training history, request `get_workout` for sessions that need deeper analysis, and call `get_workout_heart_rate` only when sample-level telemetry is useful. `get_recovery_snapshot` supplies the available sleep and recovery measurements for one date.

A good training assistant should distinguish recorded facts from inference, mention missing measurements, and treat recommendations as general training guidance rather than medical advice. A durable training plan or journal is not yet stored by this server; the client or a future companion data store must retain that state.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run pixel-health-mcp --help
```

STDOUT is reserved for MCP protocol messages while `serve` is running. Send diagnostics and logs to STDERR and never print from server startup or tool calls.

Repository-specific guidance for coding agents is in [`AGENTS.md`](AGENTS.md).

## Publishing and credential safety

The source tree is intended to be safe to publish, but a repository is only safe if secrets have never been committed.

- Never place OAuth client JSON, access tokens, refresh tokens, `.env` files, or exported health data in the repository.
- The included `.gitignore` excludes common Google client-secret filenames and local development state, but it cannot recognize every custom filename.
- Inspect `git status` and the staged diff before every public push.
- If a credential was ever committed, removing the file is not enough; revoke or rotate it and remove it from Git history before publishing.
- Keep the three read-only scopes unless a user explicitly approves a broader capability and its security implications.

## Data and API notes

The implementation targets the current [Google Health API](https://developers.google.com/health), not the legacy Fitbit Web API. Available records depend on the device, account, permissions, sync status, region, and Google's API behavior. Relevant official references include the [workout data guide](https://developers.google.com/health/data-types/workouts) and [supported data types](https://developers.google.com/health/data-types).

## License

MIT. See [`LICENSE`](LICENSE).

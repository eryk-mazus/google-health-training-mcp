# Google Health MCP for Training (Unofficial)

An unofficial, local-first **Google Health MCP server** for training and recovery analysis with AI agents. It gives Codex and other Model Context Protocol clients read-only access to workouts, running sessions, heart rate, sleep, HRV, resting heart rate, respiratory rate, oxygen saturation, and VO2 max from the Google Health API v4.

Use it with health data recorded by Pixel Watch, Fitbit, and other sources synchronized to your Google Health account.

> This independent community project is not affiliated with or endorsed by Google, Fitbit, or OpenAI. It surfaces consumer health measurements for informational use and is not a medical device or medical advice.

## Why this project?

- **Training-focused tools:** start with bounded workout summaries, then inspect details and heart-rate telemetry only when useful.
- **Local OAuth credentials:** refresh tokens stay in the OS keyring or a permission-restricted user file.
- **Read-only by design:** only Google Health read scopes are requested; writes and GPS routes are excluded.
- **Agent-friendly responses:** date ranges and telemetry sizes are validated and bounded.
- **Portable:** install and run with `uv` on Python 3.11 or newer.

```text
Pixel Watch / Fitbit → Google Health account → Google Health API v4
                                             → local MCP server → Codex or another agent
```

The MCP client launches the server over STDIO when needed and stops it with the client session. It does not need to run continuously.

## Tools

| Tool | Purpose |
| --- | --- |
| `health_auth_status` | Check whether credentials exist and optionally verify them online |
| `list_workouts` | List workout summaries for an inclusive date range |
| `get_workout` | Retrieve one workout, including metrics, events, laps, and splits |
| `get_workout_heart_rate` | Retrieve bounded, downsampled heart-rate telemetry and statistics |
| `get_recovery_snapshot` | Retrieve sleep and daily recovery-related source measurements |

The server returns recorded source measurements, not a proprietary readiness score or medical diagnosis.

## Compatibility

| Client or environment | Status |
| --- | --- |
| Codex desktop / CLI on WSL | Tested |
| Other local STDIO MCP clients | Supported by the protocol; client-specific setup may vary |
| Google Health API v4 | Tested with a real Pixel Watch account |
| Remote hosted MCP | Not currently provided |

## Quickstart

Prerequisites:

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- A Google account containing Google Health data
- A Google Cloud project with Google Health API enabled
- A local MCP client such as Codex

Clone and install:

```bash
git clone https://github.com/eryk-mazus/google-health-training-mcp.git
cd google-health-training-mcp
uv sync --extra dev
```

After completing the Google OAuth configuration below, authorize and verify:

```bash
uv run google-health-training-mcp auth \
  --client-secrets /absolute/path/to/client_secret.json
uv run google-health-training-mcp auth-status --online
```

Then register the local STDIO server in Codex, using the paths returned by `command -v uv` and `pwd`:

```bash
codex mcp add google-health-training -- \
  /absolute/path/to/uv --directory /absolute/path/to/google-health-training-mcp \
  run google-health-training-mcp serve
```

Restart Codex and enter `/mcp` to confirm that `google-health-training` is connected.

## Configure Google OAuth

In [Google Cloud Console](https://console.cloud.google.com/):

1. Create or select a project and enable **Google Health API**.
2. Configure the OAuth consent screen. While the app remains in Testing status, add the Google account containing your health data as a test user.
3. Add only these scopes:
   - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
   - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
   - `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
4. Create an OAuth client of type **Web application**. The Google Health setup wizard asks for `https://www.google.com` as an authorized redirect URI; keep that entry.
5. Add this second authorized redirect URI for the automatic local callback:

   ```text
   http://127.0.0.1:8765/oauth/callback
   ```

6. Download the client JSON and keep it outside this repository.

Google permits local HTTP redirect URIs for testing, including localhost IP addresses. The callback listens only on the loopback interface and only while `auth` is running. See Google's [Google Health API setup guide](https://developers.google.com/health/setup) and [web-server OAuth redirect requirements](https://developers.google.com/identity/protocols/oauth2/web-server#creatingcred).

Refresh tokens issued to an external OAuth app in Testing status [expire after seven days](https://developers.google.com/identity/protocols/oauth2#expiration). A personal development setup may therefore require periodic reauthorization until its consent configuration is suitable for long-term use.

## Credential storage

The OS keyring is the default and recommended store. If the machine has no usable keyring backend, explicitly opt into a permission-restricted local token file:

```bash
uv run google-health-training-mcp auth \
  --credential-store file \
  --client-secrets /absolute/path/to/client_secret.json
```

On Linux, file mode defaults to `~/.local/share/google-health-training-mcp/google-oauth.json` with mode `0600`. The equivalent platform-specific user data directory is used on macOS and Windows. Configuration contains only settings and the client-secret file path; the downloaded client JSON is not copied.

Useful diagnostics:

```bash
uv run google-health-training-mcp doctor
uv run google-health-training-mcp auth-status --online
```

No command prints access or refresh token values.

### Migration from the early Pixel Health name

Development builds initially used `pixel-health-mcp`. The old executable remains as a compatibility alias, and the server automatically reads legacy environment variables, configuration, keyring entries, and token-file locations. New writes use the `google-health-training-mcp` name.

## Configure another MCP client

Configure a local STDIO server with this command and arguments:

```text
/absolute/path/to/uv --directory /absolute/path/to/google-health-training-mcp run google-health-training-mcp serve
```

The server does not use MCP-transport OAuth. Complete Google authorization with the CLI before starting the MCP server.

## Example prompts

```text
Use the Google Health training MCP to list my running workouts from the last 30 days. Show date, duration, distance, and workout ID.
```

```text
Retrieve the details and heart-rate data for workout <ID>. Summarize pace, splits, average and maximum heart rate, and clearly distinguish recorded facts from interpretation.
```

```text
Compare my recent running volume with the previous four weeks. Mention missing data and avoid medical conclusions.
```

An agent should call `health_auth_status` first, use `list_workouts` for a bounded history, and request detailed or sample-level data only when needed. This server does not currently persist a training plan, goals, or agent memory.

## Privacy and safety

- OAuth scopes are read-only.
- GPS routes are not exposed.
- Tokens never appear in MCP responses.
- Raw health data is fetched only when an MCP tool requests it.
- Tool output is passed to the connected agent and its model provider as part of the conversation; use a provider and retention configuration appropriate for your privacy needs.
- Health measurements and agent interpretations are not medical advice.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run google-health-training-mcp --help
```

STDOUT is reserved for MCP protocol messages while `serve` runs. Send diagnostics and logs to STDERR.

Repository-specific guidance for coding and runtime agents is in [`AGENTS.md`](AGENTS.md).

## Publishing and credential safety

The source tree is intended to be safe to publish, but a repository is only safe if secrets have never been committed.

- Never place OAuth client JSON, access tokens, refresh tokens, `.env` files, or exported health data in the repository.
- `.gitignore` excludes common Google client-secret filenames and local development state, but cannot recognize every custom filename.
- Inspect `git status` and the staged diff before every public push.
- If a credential was committed, revoke or rotate it and remove it from Git history before publishing.
- Keep the three read-only scopes unless a user explicitly approves a broader capability and its security implications.

## FAQ

### Is this an official Google or Fitbit project?

No. It is an independent, unofficial open-source integration.

### Does it work only with Pixel Watch?

No. It queries the Google Health account authorized through OAuth. Available records depend on the device, account, sync status, permissions, region, and Google Health API behavior.

### Is this the same as Health Connect on Android?

No. This project calls the cloud-based Google Health API v4. It does not read the on-device Android Health Connect database directly.

### Does the MCP save my training plan?

Not yet. It supplies health context to an agent; durable plans or journals require the MCP client or a future companion store.

### Why are GPS routes excluded?

Location data is more sensitive and is unnecessary for the initial training-summary use cases. Route access may be considered later as a separate, explicit opt-in capability.

## API references

The implementation targets the current [Google Health API](https://developers.google.com/health), not the legacy Fitbit Web API. See the official [workout guide](https://developers.google.com/health/data-types/workouts) and [supported data types](https://developers.google.com/health/data-types).

## License

MIT. See [`LICENSE`](LICENSE).

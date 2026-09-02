# AGENTS.md

## Project purpose

This repository implements **Google Health MCP for Training (Unofficial)**, a local, read-only MCP server for a user's Google Health training and recovery data. The primary clients are coding or personal-assistant agents such as Codex. Preserve user privacy, predictable tool schemas, and bounded responses over feature breadth.

The project targets the current Google Health API at `health.googleapis.com/v4`. Do not add integrations against the legacy Fitbit Web API.

## Repository map

- `src/google_health_training_mcp/server.py`: MCP server and public tools
- `src/google_health_training_mcp/google_health.py`: Google Health REST client, filters, and transformations
- `src/google_health_training_mcp/normalization.py`: additive numeric workout, split, and event normalization
- `src/google_health_training_mcp/auth.py`: OAuth flow, token refresh, and credential storage
- `src/google_health_training_mcp/config.py`: platform-specific configuration, data paths, and legacy-name fallback
- `src/google_health_training_mcp/cli.py`: authorization, diagnostics, logout, and STDIO entry points
- `tests/`: offline unit and MCP discovery tests

## Setup and verification

Use `uv`; do not document environment-specific virtual-environment paths.

```bash
uv sync --extra dev
uv run pytest
uv run google-health-training-mcp --help
uv run google-health-training-mcp doctor
```

Tests must be offline, must not open a browser, and must not load, overwrite, or delete real user credentials. Mock HTTP, filesystem, keyring, and credential boundaries for integration tests.

## Naming and compatibility

- The public project, package, and primary CLI name is `google-health-training-mcp`.
- The display name is `Google Health MCP for Training (Unofficial)`.
- Keep `pixel-health-mcp` only as a transitional CLI/config compatibility alias until a documented breaking release removes it.
- New configuration and tokens use `google-health-training-mcp`; reads may fall back to legacy Pixel-named locations.
- Always retain the unofficial/non-affiliation disclaimer. Do not use Google or Fitbit logos or imply endorsement.

## Security and privacy invariants

- Google API access is read-only. Do not add write scopes or mutation tools without explicit user authorization and a clear security review.
- Do not expose GPS/location data by default.
- Never log, print, return, snapshot, or commit OAuth access tokens, refresh tokens, authorization codes, client secrets, or raw HTTP authorization headers.
- Store credentials in the OS keyring by default. The explicit file fallback must remain outside the repository and permission-restricted where the operating system supports Unix modes.
- Keep client-secret files and health-data exports outside the repository. Do not weaken the related `.gitignore` rules.
- Validate identifiers, date ranges, pagination, and sample limits. Keep MCP responses bounded.
- Avoid medical diagnosis or claims. Clearly separate recorded measurements, calculations, inferences, and general training guidance.

## MCP implementation rules

- STDOUT belongs exclusively to the MCP protocol while `serve` is running. Logs and diagnostics must go to STDERR.
- Keep existing tool names and response fields backward compatible when practical. Additive changes are safer than silent semantic changes.
- Declare data-access tools as read-only and open-world in MCP annotations.
- Tool descriptions should state date formats, defaults, limits, and important omissions so an agent can call them safely without reading source code.
- Prefer summary tools before high-volume telemetry. Downsample time series and report whether results were bounded.
- Return actionable errors without including credentials or unnecessary personal data.
- Use official Google Health and MCP documentation when an API detail is uncertain; do not guess request paths, filters, scopes, or schemas.

## Runtime guidance for agent clients

When using this MCP to help with training:

1. Call `health_auth_status` before the first data request. Use online verification only when credential freshness is relevant.
2. Call `list_workouts` with the smallest useful date range and limit.
3. Use `get_workout` only for sessions that need detailed metrics, laps, splits, or events.
4. Use `get_workout_heart_rate` only when sample telemetry affects the analysis; request a modest sample limit first.
5. Use `get_recovery_snapshot` for a specific date and explicitly note unavailable data types.
6. Cite the workout/date behind conclusions, distinguish facts from inferred trends, and never present output as medical advice.

This server does not currently persist a training plan, goals, or agent memory. An agent must not imply that such state was saved unless another configured system actually stored it.

## Change discipline

- Keep the README directory-agnostic, search-friendly, and suitable for a public repository.
- Update README tool documentation and discovery tests whenever the public MCP surface changes.
- Add focused tests for parsing, filters, pagination, response bounding, credential migration, and error redaction.
- Run the full offline test suite before handing off a change.

# Changelog

## [0.5.5] - 2026-08-19

### What changed
- Fixed `npg_ban_ip`: the request body sent the key `duration` while the NPG API binds `ban_time`. Go silently ignored the unknown key, so `ban_time` defaulted to 0 and **every manual ban was created as PERMANENT** regardless of the requested duration. The parameter is renamed to `ban_time` (seconds, 0=permanent, default 3600) and the body now sends `ban_time`. Live-confirmed on the v2.45.0 test stack: `ban_time=3600` now returns `is_permanent: false` with an `expires_at`.
- Added `npg_update_ban_duration` for the new upstream v2.45.0 endpoint `PUT /api/v1/banned-ips/{id}/duration`: re-dates an existing ban. `ban_time` counts from NOW (not from when the ban started) and 0 makes it permanent. nginx configs are not regenerated.
- Updated `npg_update_proxy_host_fail2ban` description: `ban_time` is seconds, 0=permanent (upstream `CreateFail2banRequest.ban_time` is now a pointer — omitted keeps the stored value, 0 persists as permanent on update).

### What's new
- `npg_update_ban_duration` — change how long an existing ban still runs (seconds from now; 0 = permanent ban).

### Breaking changes
- `npg_ban_ip` parameter renamed `duration` → `ban_time`. Callers passing the old `duration` name now get a validation error; update call sites. This fixes the silent permanent-ban bug for existing callers.

## [0.5.4] - 2026-08-19

### What changed
- Added two targeted bulk tools that loop the existing per-host endpoints in a single MCP call, avoiding N+1 round-trips: `npg_bulk_apply_certificate` (PUT `/api/v1/proxy-hosts/{id}` with the certificate on each host, confirmed via follow-up GET) and `npg_bulk_delete_proxy_hosts` (DELETE `/api/v1/proxy-hosts/{id}` per host). Both are capped at 50 host IDs per call (exceeding the cap is rejected up front), do not abort on a per-host error, and are classified as destructive tools so they are hidden at the `standard` tool level.
- Added per-request correlation IDs to MCP logging: the access-log middleware generates `req=<8-hex>` per inbound MCP request and propagates it via ContextVars so both the access log and the error log for one request share the same correlation ID.
- Added ruff linting (E, F, W, I rulesets) and non-strict mypy type-checking to the CI `validate` job in `.github/workflows/publish.yml`, with `ruff` and `mypy` added to the dev optional dependencies and tuned `[tool.ruff]`/`[tool.mypy]` config.
- Added a real HTTP `/health` endpoint (`_health_app`, Starlette route) so Docker container healthchecks are meaningful: returns `200 {"status":"ok","tools":<exposed count>,"npg_reachable":true}` when healthy and `503` JSON when NPG is unreachable.

### What's new
- `npg_bulk_apply_certificate` — apply one certificate to multiple proxy hosts in a single MCP call.
- `npg_bulk_delete_proxy_hosts` — delete multiple proxy hosts in a single MCP call.
- HTTP `/health` endpoint on the MCP server for real container healthchecks.

### Breaking changes
- (none)

## [0.5.3] - 2026-08-18

### What changed
- `DESTRUCTIVE_TOOLS` is now auto-derived at import time from tool name prefixes instead of a hand-maintained 46-entry frozenset. A documented regex (`^npg_(delete_|remove_|ban_|bulk_unban_|cleanup_|reset_|restore_|revoke_|rotate_log|set_user_(password|role|email)|upload_restore_backup)`) plus empty allowlist/denylist escape hatches classify destructive tools, so new destructive tools are hidden at the `standard` tool level automatically without manual list maintenance.
- Added pytest coverage for the derivation logic (`tests/test_toolsets.py`), including the allowlist/denylist escape hatches and the `tier_allowed` helper; the full suite (79 tests incl. 20 toolset tiers) passes.
- Verified end-to-end on a HEAD-pinned local image against the test stack: `full`=276 tools, `standard`=230 with zero destructive leaks (e.g. `npg_ban_ip` → "Unknown tool"), `read`=129 with zero mutation leaks; regression checks `npg_list_proxy_hosts` / `npg_get_settings` pass.

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.2] - 2026-08-17

### What changed
- The GitHub Actions publish workflow now prefers curated release notes: it extracts the `## [version]` section from CHANGELOG.md (with `### What changed` / `### What's new` / `### Breaking changes` subsections) and passes it to `gh release create --notes-file`; when that section is missing or malformed it falls back to auto-generated notes. This keeps the release page in sync with the curated changelog instead of dumping raw commit subjects.

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.1] - 2026-08-17

### What changed
- Added input validation helpers (`_validate_id` / `_validate_required`) so ID parameters and required fields are checked up front and return clear `success: false` errors instead of opaque API failures.
- Added a shared `_build_body` helper to eliminate duplicated `if x is not None:` conditional body-building code across update tools, keeping partial-update semantics consistent.
- Added a pytest unit test suite (`tests/`) covering the HTTP client, toolset registration, and main.py helpers; 74 tests pass.

### What's new
- Added `npg_create_proxy_host_simple` and `npg_update_proxy_host_simple` — 8-parameter core tools for the most common proxy-host operations, for callers who don't need the full 52-parameter surface. Use the full `npg_create_proxy_host` / `npg_update_proxy_host` for advanced options.

### Breaking changes
- (none)

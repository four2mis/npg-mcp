# Changelog

## [0.5.8] - 2026-08-20

### What changed
- Synced the MCP wrapper with upstream NPG v2.46.0: the rate-limit exception list became a real nullable field upstream, so `npg_update_proxy_host_rate_limit` and `npg_update_global_rate_limit` now expose a `whitelist_ips` parameter (`str | None`). Semantics: omit = keep the stored list, `""` = clear it, otherwise comma/newline-separated IPs or CIDRs (an invalid entry is rejected with HTTP 400). Tool descriptions updated to match.
- Committed the upstream v2.46.0 swagger.yaml so the API reference tracks the synced version.

### What's new
- `whitelist_ips` parameter added to `npg_update_proxy_host_rate_limit` and `npg_update_global_rate_limit`.

### Breaking changes
- (none)

## [0.5.7] - 2026-08-20

### What changed
- Trimmed 22 oversized tool descriptions (>300 chars) to <=299 chars so every tool description fits the MCP description field limit and stays useful to agents. Longest went from 1235 chars (npg_update_proxy_host) and 1029 (npg_create_proxy_host) down to ~285-291. Description-only edits — no signature or behavior changes (verified backward compatible).
- Fixed the `limit`/`offset` query-parameter mapping on the proxy-hosts and logs list tools: the NPG API binds `per_page`/`page`, so the previously sent `limit`/`offset` were silently ignored. The list tools now translate to the API's native parameters (verified against the running fork).
- Added pagination and filter query parameters to 4 list tools with conditional parameter building and non-negative-integer validation: `npg_list_proxy_hosts`, `npg_get_logs`, `npg_list_audit_logs`, `npg_list_system_logs`. Callers can now pass `limit`/`offset` (mapped to `per_page`/`page`) plus per-tool filters instead of fetching full unpaginated result sets.
- Added `npg_bulk_renew_certificates` with a 20-certificate batch cap (`_BULK_CERT_LIMIT`) and per-certificate error isolation, mirroring `npg_bulk_delete_proxy_hosts`: one failing certificate does not abort the batch, and each result reports success/error individually.

### What's new
- `npg_bulk_renew_certificates` — renew many certificates in a single MCP call (batch cap 20, per-cert error isolation).
- Pagination/filter support on list tools: `npg_list_proxy_hosts`, `npg_get_logs`, `npg_list_audit_logs`, `npg_list_system_logs` now accept `limit`/`offset` (mapped to `per_page`/`page`) and relevant filter parameters.

### Breaking changes
- (none)

## [0.5.6] - 2026-08-20

### What changed
- Fixed `npg_upload_certificate_pem`: the request body sent the key `pem`, which the NPG API ignores; it now sends the correct `certificate_pem` + `private_key_pem` fields. The `private_key_pem` parameter is now required and validated.
- Fixed `npg_add_filter_subscription_entry_exclusion` / `npg_remove_filter_subscription_entry_exclusion`: the body sent `entry_value` but the NPG API binds `value` (request-body field on add, query parameter on remove), so exclusions were silently not applied. Both now send `value`.
- Fixed `npg_update_global_waf`: removed the phantom `rules` field (ignored by the upstream request model) and added the `mode` parameter (`detection|blocking`) that the API actually accepts; `paranoia_level` (1-4) is now documented.
- Fixed `npg_update_proxy_host_upstream` description to match the real API contract: each server entry has separate `address` and `port` fields plus `weight` and `is_backup` — the port must no longer be embedded in the address string.
- Fixed `npg_auth_sso_start`: the SSO start endpoint answers with a 302 redirect to the identity provider, which previously surfaced as an error. `NPGClient.get()` now supports `redirect_ok=True` and returns the `Location` header as `{"redirect_url": ...}`. Redirects are never followed, so the API token is never forwarded to an external IdP.

### What's new
- (none)

### Breaking changes
- `npg_upload_certificate_pem` now requires `private_key_pem` — callers passing only `pem_content` will get a validation error; pass both the certificate and private key PEM strings.
- `npg_update_global_waf` no longer accepts the `rules` parameter (it was silently ignored by the API) and gains `mode`; callers passing `rules` will get a validation error.

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

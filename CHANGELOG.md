# Changelog

## [0.5.21] - 2026-09-01

### What changed
- Corrected the stale `description=` on `npg_rotate_log_file` in `npg_mcp/main.py` (commit fea9465): the old text claimed the tool rotates "a log file by its filename", but the tool takes NO parameters and rotates all raw log files globally. Agents reading the schema were being told to pass a filename that doesn't exist. The new description states the zero-parameter semantics, that raw log files must be enabled (upstream returns HTTP 500 "logrotate failed" otherwise), and that the call is a global rotate. Full 286-tool sweep (t_4874a076) confirmed this was the only defect; verified at wire level against a locally-built image pinned to the workspace commit.

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.20] - 2026-08-30

### What changed
- Synced the MCP wrapper to upstream NPG v2.51.0. `npg_update_system_settings` now accepts the 3 new `UpdateSystemSettingsRequest` fields in its kwargs whitelist: `trusted_proxy_cidrs` (newline-separated IP/CIDR list), `trusted_proxy_preset` (none|cloudflare), and `real_ip_header` (X-Forwarded-For|X-Real-IP|CF-Connecting-IP|True-Client-IP). Previously, strict=true calls containing these fields were rejected client-side by the stale whitelist.
- `npg_get_logs` gained 3 new query filters mirroring upstream `parseLogFilter` (v2.51.0): `status_classes` (list of 1xx-5xx class tokens), `exclude_status_codes` (list of ints), and `exclude_status_classes` (list of tokens). Upstream validates all filter values server-side — invalid values now surface as clean HTTP 400 errors naming the offending token instead of being silently dropped.
- Tool descriptions for `npg_create_exploit_rule` and `npg_update_exploit_rule` now document the rewritten v2.51.0 validation: severity enum is `info|warning|critical` (default warning; legacy `low`/`medium`/`high` return 400), `pattern_type` is strictly enforced, `name` is capped at 100 chars, and regex patterns are validated.

### What's new
- Real-IP / trusted-proxy configuration is now reachable through the MCP API: set `trusted_proxy_cidrs`, `trusted_proxy_preset`, and `real_ip_header` via `npg_update_system_settings` to make NPG trust proxy-provided client IPs (e.g. behind Cloudflare).

### Breaking changes
- Callers passing `severity="low"`, `"medium"`, or `"high"` to exploit-rule tools will now get HTTP 400 from upstream — use `info`, `warning`, or `critical`.

## [0.5.19] - 2026-08-30

### What changed
- `npg_get_logs` now sends the query parameter `status_code` instead of `status`: upstream `parseLogFilter` reads `status_code`, so the old param was silently ignored and the HTTP status filter had no effect. Verified against the test stack — `status=200` now returns only the matching log rows, and combined host/method/status filters work.
- Dropped phantom request fields from 4 tools that upstream v2.50.0 request models don't define (fields were silently ignored by Go): `npg_create_certificate` lost the `email` param (ACME email comes from system settings via `npg_update_system_settings(acme_email=...)`), `npg_create_log_filter_preset` lost `description`, `npg_update_log_filter_preset` no longer sends `description` (a description-only PUT triggered upstream 400 "nothing to update"), and `npg_update_challenge_config` lost the `provider` param. Descriptions updated in the same commit per the CI description-sync gate.

### What's new
- (none)

### Breaking changes
- `npg_create_certificate` no longer accepts an `email` parameter — set the ACME contact email once via `npg_update_system_settings(acme_email=...)` instead.
- `npg_create_log_filter_preset` / `npg_update_log_filter_preset` no longer accept a `description` parameter, and `npg_update_challenge_config` no longer accepts a `provider` parameter — these fields never existed upstream, so callers passing them were no-ops.

## [0.5.18] - 2026-08-28

### What changed
- swagger.yaml synced to upstream NPG v2.50.0 (version string + trailing newline only). Upstream v2.50.0 is a server-side release (nginx/WAF/fail2ban runtime fixes) with zero API contract changes — no MCP tool code changes were needed.

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.17] - 2026-08-28

### What changed
- `npg_update_proxy_host_fail2ban` now accepts `action` values `block`, `log`, and `notify` (upstream NPG v2.50.0 added server-side validation: `challenge` is rejected with 400, and `notify` is a distinct no-ban action). Tool description documents the three actions and the new `fail_codes` validation (typo'd codes like `4o1` are rejected at save time).

### What's new
- Fail2ban "Notify Only" (action=`notify`) and "Log Only" (action=`log`) semantics are now reachable through the MCP tool, matching upstream v2.50.0 behavior where `notify` alerts without banning instead of silently banning.

### Breaking changes
- Callers passing `action="challenge"` to `npg_update_proxy_host_fail2ban` will now fail: the upstream API rejects `challenge` for fail2ban (HTTP 400) — use `block` for blocking behavior.

## [0.5.16] - 2026-08-25

### What changed
- Blocking `NPGClient` HTTP calls are now offloaded to worker threads via `asyncio.to_thread`, so slow upstream responses no longer freeze the MCP server's asyncio event loop (other tool calls and health checks stay responsive).
- Binary download tools are now binary-safe: `NPGClient.get_bytes()` returns raw bytes plus content-type, and `npg_download_backup` / `npg_get_certificate_download` return gzip/zip payloads base64-encoded (`encoding=base64`) instead of crashing on non-JSON bodies.
- kwargs dicts passed to the 11 pass-through update/create tools are now whitelist-validated against the upstream v2.48.0 Go request structs before any API call: a misspelled or phantom field raises immediately with the accepted-field list instead of being silently ignored by the API (the classic silent-noop bug class). A `strict=false` escape hatch allows bypassing validation when needed.

### What's new
- `strict` escape-hatch parameter on kwargs-whitelisted tools to skip validation for forward-compatibility.
- New `NPGClient.get_bytes()` method for binary-safe HTTP downloads.

### Breaking changes
- kwargs-based tools now reject unknown field names with an error listing accepted fields; callers passing previously-silently-ignored typos must fix the field names or set `strict=false`.
- (none)

## [0.5.15] - 2026-08-24

### What changed
- HTTP GET requests now automatically retry on 429 Too Many Requests, honoring the upstream `Retry-After` header (capped at 10s) with exponential backoff as fallback. This makes bulk tool sweeps and busy-period calls resilient to NPG API rate limiting instead of failing outright.
- The httpx request timeout is now configurable via `NPG_HTTP_TIMEOUT` (seconds, default 30, clamped to [1,600]; invalid values fall back to 30 with a warning). Documented in `.env.example` and both READMEs.
- Trimmed 10 oversized MCP tool descriptions toward the ~250-char guideline (largest was 882 chars). No signatures or behavior changed; `tool-schemas.yaml`, `README.md`, and `README.ko.md` regenerated in sync.
- Repo hygiene: removed kanban scratch scripts from the repo and added `.kanban-tmp/` to `.gitignore`.

### What's new
- `NPG_HTTP_TIMEOUT` environment variable for tuning per-request timeout.
- Automatic 429 retry with Retry-After awareness on all GET/get_text calls.

### Breaking changes
- (none)

## [0.5.14] - 2026-08-24

### What changed
- `npg_get_proxy_host_full` now accepts an optional `sections` filter so agents can fetch only the per-host sub-configs they actually need (e.g. just `waf` + `rate_limit`) instead of every sub-resource GET on each call. Entries are validated (unknown names raise a clear error listing valid values) and de-duplicated preserving order; failed sections are reported individually instead of failing the whole call. Verified end-to-end on the isolated test stack against a HEAD-pinned local build: 16/16 live MCP checks including zero-arg, filtered, dedupe, invalid-section, and failed-section behavior plus a 4-tool regression sample; 175 pytest pass; docs in sync.
- Added `npg_enable_waf_rule` to complete the enable/disable pair for per-host WAF rules — enabling is a `DELETE /waf/hosts/{id}/rules/{rid}/disable` (removing the exclusion), mirroring the existing global-rule tool. Enabling a rule that was never disabled surfaces upstream HTTP 500, which the tool description documents.

### What's new
- `npg_get_proxy_host_full(sections=[...])` optional filter parameter (tool count 285 → 286 with npg_enable_waf_rule).
- `npg_enable_waf_rule` — re-enable a per-host disabled WAF rule via DELETE /waf/hosts/{id}/rules/{rid}/disable.

### Breaking changes
- (none)

## [0.5.13] - 2026-08-23

### What changed
- New `npg_bulk_import_proxy_hosts` tool creates many proxy hosts from one CSV payload in a single call: per-row failure isolation (one bad row doesn't abort the batch), strict header validation before any API call, 50-row cap, and per-row result entries with created/failed summary. Boolean columns accept true/false/1/0/yes/no/on/off (typos fail only their row); empty optional cells inherit global defaults; `skip_nginx=true` (default) leaves nginx unsynced until an explicit `npg_sync_nginx` call. Verified on the isolated test stack against a local build pinned to the workspace commit: 8/8 E2E checks (CSV create, per-row failure isolation, header validation, 50-row limit), 8/8 unrelated-tool regression sample, 169 pytest pass, docs in sync.

### What's new
- `npg_bulk_import_proxy_hosts` — bulk-create proxy hosts from CSV text (tool count 284 → 285).

### Breaking changes
- (none)

## [0.5.12] - 2026-08-23

### What changed
- Four new read-only self-test tools wrap the upstream NPG v2.46.0 `test/*` endpoints, letting an MCP agent run the same health diagnostics the NPG UI exposes without raw HTTP access. All four are GET-style/read-only (the backup round-trip test creates and deletes only a throwaway row; the nginx-config test is a dry-run `nginx -t` with no reload). Each tool's description documents its side-effect profile and next-step tools. Verified on the isolated test stack: live positive paths pass, regression tools pass, pytest suite green, docs regenerated in sync.

### What's new
- `npg_validate_nginx_config` — POST /api/v1/test/nginx-config dry-run `nginx -t`; validates config validity with NO reload.
- `npg_system_self_check` — GET /api/v1/test/system/self-check one-shot diagnostic (DB + nginx -t + backup dir).
- `npg_check_backup_restore` — GET /api/v1/test/backup-restore backup create/list/delete round-trip self-test (throwaway row only, no archive/restore).
- `npg_check_dashboard_queries` — GET /api/v1/test/dashboard/queries dashboard aggregation-query self-test. Tool count 278 → 282.

### Breaking changes
- (none)

## [0.5.11] - 2026-08-23

### What changed
- `npg_upload_restore_backup` now takes an explicit `encoding` parameter (`base64` | `raw`, default `base64`) instead of trial-decoding the payload as base64. Decoding uses `validate=True`, so invalid base64 is rejected with a clear error instead of being silently misinterpreted, and `encoding="raw"` passes the bytes through byte-for-byte — fixing restores of binary (true gzip) backup payloads that previously got mangled by ambiguous auto-detection. Verified live on the test stack: default and explicit `base64` restores succeed against a true gzip backup, raw mode is a byte-for-byte passthrough, invalid encoding values and invalid base64 are rejected explicitly.

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.10] - 2026-08-23

### What changed
- `npg_test_nginx` is now a true read-only test: it calls `POST /test/nginx-config` (runs `nginx -t` against the current config and returns validity) instead of `POST /proxy-hosts/sync`, which regenerated ALL enabled hosts and reloaded nginx — a deploy disguised as a test. Verified live on the test stack: config-valid result with no sync triggered.
- Dockerfile runtime dependency aligned with `pyproject.toml`: `mcp>=1.29.0,<2.0.0` instead of the old pin, so the image and the package metadata agree on the supported mcp range.
- Added `.dockerignore` so the docker build context stops shipping credentials (`.env*`), git history, venvs, tests, and other repo noise — smaller, safer builds.
- Fixed stale hardcoded tool counts (280) in `tests/test_health.py` and `tests/test_toolsets.py` to the current count (278) left behind by the earlier duplicate-tool removal.

### What's new
- (none)

### Breaking changes
- Removed exact-duplicate tools `npg_check_npg_update` (identical to `npg_check_update`) and `npg_get_notification_channel_deliveries` (identical to `npg_get_notification_deliveries`); tool count 280 → 278. Use the canonical names.

## [0.5.9] - 2026-08-21

### What changed
- `npg_create_proxy_host_simple` now enables the WAF by default: new `waf_enabled` and `waf_use_global` parameters (both default `true`), matching the security posture of the full `npg_create_proxy_host` tool and every other host in a default stack. Previously the simple tool never sent WAF fields, so new hosts silently shipped with `waf_enabled: false` while the rest of the setup ran with WAF on. Both fields are sent to the NPG API only when a value is provided; the hardcoded default `true` means callers who omit them get WAF-on with global inherit. Callers who explicitly want WAF off can pass `waf_enabled=false` (the existing `false`-flow is preserved by `_build_body` skipping only `None`, not `False`).

### What's new
- `waf_enabled` (default `true`) — toggle NPG WAF on the new host.
- `waf_use_global` (default `true`) — inherit the global WAF settings block.

### Breaking changes
- (none) — additive, backward compatible. Only effect on existing behavior: new hosts created via the simple tool now inherit global WAF instead of shipping WAF-disabled.

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

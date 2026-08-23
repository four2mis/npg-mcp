# Changelog

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

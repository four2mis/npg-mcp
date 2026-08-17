# Changelog

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

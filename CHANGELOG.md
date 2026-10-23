# Changelog

## [1.1.2] - 2026-10-23

### What changed
- Removed the 4 deprecated alias tools that were marked as exact route+behavior duplicates in v1.1.0 (commit 87288a4). Tool count drops 312 → 308; per-tier counts drop to read=139 / standard=261 / full=308 and the tier-count block in `.env.example` was updated in the same commit.
- Regenerated `tool-schemas.yaml`, `README.md`, and `README.ko.md` from source in the same commit; toolset/dry-run/health tests were updated for the removal (pytest 445/445 passing).
- Verified on the isolated test stack against a local HEAD build (local/npg-mcp:87288a4): server serves 308 tools with all 4 aliases absent, 6/6 sampled MCP tool calls succeed, prose-drift `--check` exits 0 with all 5 rules passing.

### What's new
- (none)

### Breaking changes
- Removed `npg_sync_nginx` and `npg_reload_nginx` — use `npg_sync_proxy_hosts` (single sync+test+reload call).
- Removed `npg_test_nginx` — use `npg_validate_nginx_config`.
- Removed `npg_enable_waf_rule_by_host` — use `npg_enable_waf_rule` (the removed alias called a non-existent `POST /enable` upstream path; the canonical tool enables via `DELETE` on the `/disable` path).

## [1.1.1] - 2026-10-23

### What changed
- Publish workflow doc-drift gate now accepts the Korean category-count unit (N개) in README.ko.md, so the compact bilingual README format no longer trips the CI validate step (commit 773c20a).
- Wrapped 5 over-length assert lines in tests/test_list_pagination.py to satisfy ruff E501; test logic unchanged (commit 7bc8dd1).

### What's new
- (none)

### Breaking changes
- (none)

## [1.1.0] - 2026-10-21

### What changed
- Exposed five previously hidden upstream NPG query capabilities as optional MCP tool parameters, after upstream route/struct review confirmed the API already supports them. All new params are optional with `None` defaults — omitted params hit the API byte-identically to before (no behavior change for existing callers); every signature change carries a description update in the same commit (publish.yml validate gate).
- Tool-surface audit follow-up: marked 5 exact route+behavior duplicate tools as deprecated aliases in their descriptions (commit 7d4ef6f). Canonical picks — `npg_sync_proxy_hosts` over `npg_sync_nginx`/`npg_reload_nginx`, `npg_validate_nginx_config` over `npg_test_nginx`, `npg_enable_waf_rule` over `npg_enable_waf_rule_by_host`. No signatures, routes, tiers, or tool count changed (312 tools throughout); aliases are slated for removal in a later minor release.
- README accuracy pass (commit 56af7e8, both languages): tool naming fixed to `mcp__npg_mcp__*`, dependency pin corrected to `mcp>=1.29.0,<2.0.0`, MCP_TRANSPORT defaults documented (bare process = stdio, Docker image = http), Quick Start now shows explicit env export (`source .env` is NOT auto-loaded — no dotenv dep), added version-pinned image pull and a Development & Testing section.

### What's new
- New capability: `npg_list_proxy_hosts` gained `sort_by` (name|created|updated) and `sort_order` (asc|desc) — server-side proxy host sorting (commit b3cd521).
- New capability: `npg_get_audit_log_api_tokens` gained `limit`/`offset` paging via the `_list_params` helper, so large audit tables can be paged instead of pulled whole (commit d52863d).
- New capability: the 4 log autocomplete tools (`npg_get_log_autocomplete_hosts/ips/uris/user_agents`) gained `q` (substring filter) and `limit` params (commit d296893).
- New capability: `npg_get_certificate_history` gained `certificate_id` (scopes history to one certificate) and `limit` (maps to upstream `per_page`) (commit e6a20a2).

### Breaking changes
- (none — all new parameters are optional; omitted params behave exactly as before)

## [1.0.0] - 2026-10-20

### What changed
- Version-scheme migration: the 0.5.x numbering is retired at 0.5.47. The minor version had been frozen since 0.5.0 while the patch counter grew to 47 (86 releases total since 2026-08-02), so the "0.5.x" label no longer carried any meaning about change size. From this release on, the project follows the user-approved 1.0.x scheme: bug-fix/doc/internal releases bump the patch digit (1.0.0 → 1.0.1), releases that add tools or capabilities — including upstream NPG feature syncs — bump the minor digit and reset the patch (1.0.5 → 1.1.0), and the major digit moves only on deliberate, user-directed exceptions. This release changes version metadata and release automation only; the shipped code is identical to v0.5.47 (commit ef073cd).
- Release-task automation (repo-external, npg-kanban-pipeline.py): the release task template now spells out the patch/minor bump rules and adds a post-push verification leg — poll the `publish.yml` run, confirm tag + release notes exist, and verify the GHCR bare-tag digest match via `verify_ghcr_release.sh` — so a failed/missing publish surfaces in the same run instead of days later.

### What's new
- (none — scheme-migration release; the MCP tool surface is byte-identical to v0.5.47: 312 tools, read=139 / standard=265 / full=312)

### Breaking changes
- (none — no tool, parameter, or configuration changes; existing `0.5.x` image references keep working and `latest` now tracks v1.0.0)

## [0.5.47] - 2026-10-19

### What changed
- Fixed 7 MCP-layer phantom-field / field-mapping bugs found by the static preflight (task t_b191add1), each verified against upstream NPG v2.64.0 Go request structs (svrforum/NginxProxyGuard @ 71fdb608). Class of bug: Go silently drops unknown JSON keys, so callers saw success while nothing was applied (or, worse, unrelated settings were wiped).
- `npg_create_api_token`: body param `expires_at` renamed to `expires_in` (upstream `CreateAPITokenRequest` has no `expires_at`); format `'<n>'+unit` (e.g. `30d`, `1y`, `12h`) or `never`; omitted = never expires.
- `npg_create_user`: removed the `is_active` param — upstream `CreateUserRequest` is `{username, password, role_id, email}` and created users are active immediately. Body no longer sends `is_active`.
- `npg_update_system_settings_logs`: the 3 phantom params (`max_age`/`max_size`/`max_files`) are replaced with the real config fields (`enabled`, `levels`, `exclude_patterns`, `stdout_excluded`). The tool now does READ-MODIFY-WRITE: upstream binds a full-value `SystemLogConfig` struct on PUT, so any partial body writes absent keys as zero values and DISABLES the container log collector. Zero-field calls are rejected; disabling requires explicit `enabled=false`.
- `npg_create_proxy_host` / `npg_update_proxy_host`: removed 4 phantom params (`block_normal`, `block_http`, `cache_template`, `enable_proxy_headers`) — zero occurrences anywhere in upstream v2.64.0 (all .go + swagger.yaml); those body keys were silently dropped by Go.
- `npg_bulk_import_proxy_hosts`: dropped the `block_normal` CSV column (fed the phantom create param); the tool description now lists the exact accepted columns.
- `npg_update_filter_subscription`: removed the `url` param (URL is create-only upstream — every `url` update silently no-oped) and added the 3 real optional params `refresh_type` (`interval`/`daily`/`cron`), `refresh_value` (interval: `6h`/`12h`/`24h`/`48h`; daily: `HH:MM`; cron: cron expression) and `exclude_private_ips`.
- All 7 signature changes carry description updates in the same commit (publish.yml validate gate); `tool-schemas.yaml`, `README.md` and `README.ko.md` regenerated (`--check` in sync); `tests/test_bulk_import.py` updated to assert the phantom body field is absent.

### What's new
- `npg_update_filter_subscription` gained `refresh_type` / `refresh_value` / `exclude_private_ips` — refresh schedules and private-IP exclusion were previously unmanageable through MCP.
- `npg_update_system_settings_logs` gained the only reachable log-collector params (`enabled`, per-container `levels`, `exclude_patterns`, `stdout_excluded`); updates now round out the live config instead of risking disabling the collector.

### Breaking changes
- `npg_create_api_token`: parameter `expires_at` is gone — send `expires_in` (duration string like `30d`/`1y`/`never`) instead.
- `npg_create_user`: parameter `is_active` is gone (upstream always activates new users).
- `npg_create_proxy_host` / `npg_update_proxy_host`: parameters `block_normal`, `block_http`, `cache_template`, `enable_proxy_headers` are gone — they never had any upstream effect.
- `npg_update_filter_subscription`: parameter `url` is gone — the list URL can only be set at create time.
- Bulk-import CSV: the `block_normal` column is no longer routed to the create call (it was always a no-op); CSVs carrying it still import fine with the column ignored.

## [0.5.46] - 2026-10-19

### What changed
- Synced the MCP wrapper with upstream NPG v2.64.0 (commit 68b12f4): the geo / rate-limit / URI-block / trusted IP exception lists now accept **hostname (DDNS domain-name) entries** in addition to IP/CIDR entries, and 5 new DNS-confirm tools were added. `swagger.yaml` re-synced to the v2.64.0 spec (+628 lines).
- Hostname support is exposed on the existing mutating tools as new partial-update params: `allowed_hostnames` on `npg_create_proxy_host_geo` / `npg_update_proxy_host_geo` / `npg_update_global_geo`, `whitelist_hostnames` on `npg_update_proxy_host_rate_limit` / `npg_update_global_rate_limit`, `exception_hostnames` on `npg_update_proxy_host_uri_block` / `npg_update_global_uri_block`, and `global_trusted_hostnames` via the `npg_update_system_settings` kwargs whitelist. Each follows the established partial-update contract — omit = keep the stored list, `[]` = clear.
- `npg_update_system_settings` now whitelists the new `global_trusted_hostnames` kwargs key in `npg_mcp/upstream_models.py`.
- Regenerated `tool-schemas.yaml` + `README.md` + `README.ko.md` after the sync (commit 348a59f): tool-schemas.yaml and both READMEs now cover all 312 tools (Proxy Hosts 45→46, Geo 10→11, Security & WAF 30→31, Settings 11→12, URI Block 6→7); doc drift check exits 0.
- Updated hardcoded unit-test guardrails (`tests/test_health.py`, `tests/test_toolsets.py`) to the new surface: 312 tools, read=139, standard=265, full=312; full pytest suite green (440 passed).
- Verified at commit 68b12f4 against the isolated test stack with a local image pinned to that exact SHA (`local/npg-mcp:68b12f4@sha256:5d7013df…`, task t_a23806a7): a 30-check live sweep passed 30/30 — all 5 new `npg_confirm_*_dns` tools callable, all 7 new hostname params verified as stored on GET, 312 tools / 0 duplicate names, AST syntax OK, tier counts match (`--check-env` ✅), 11-tool regression sample clean, and cleanup confirmed (disposable host 404, globals restored).

### What's new
- New tool `npg_confirm_proxy_host_dns` — re-allow a domain entry that waits for review (`needs_review`) in a proxy host's exception lists (URI-block exceptions, priority allow, rate-limit exceptions); re-resolves the name (≤3s) and publishes only if it still matches.
- New tool `npg_confirm_trusted_dns` — same re-allow flow for the global trusted list (`system-settings` `global_trusted_hostnames`).
- New tool `npg_confirm_global_uri_block_dns` — re-allow a `needs_review` domain in the global URI-block exceptions.
- New tool `npg_confirm_global_geo_dns` — re-allow a `needs_review` domain in the global priority allow list (global GeoIP `allowed_hostnames`).
- New tool `npg_confirm_global_rate_limit_dns` — re-allow a `needs_review` domain in the global rate-limit exceptions.
- New capability: domain (DDNS) name entries in allow / exception / whitelist / trusted lists — a domain name whose resolved addresses count as the corresponding IP entry, managed via the new `*_hostnames` params and confirmed via the 5 `npg_confirm_*_dns` tools.

### Breaking changes
- Domain names are no longer accepted in the IP/CIDR list fields: sending a hostname in `whitelist_ips`, `allowed_ips`, `exception_ips`, or `global_trusted_ips` now returns HTTP 400 `hostname_in_ip_field`. Use the corresponding new `*_hostnames` parameter instead.

## [0.5.45] - 2026-10-17

### What changed
- Synced the MCP wrapper with upstream NPG v2.63.0 (commit 4e60684): 3 new API endpoints gained MCP tools, and `npg_update_system_settings` now whitelists the new `dns_entry_settings` kwargs block (DNS entry limits accept values 1–256; verified live: 64→90 set, out-of-range 999 rejected with the documented API 400).
- `npg_update_system_settings` now whitelists `dns_entry_settings` (DNS entry limit + status; partial object — an omitted or null key keeps its stored value). Descriptions of `npg_update_settings`-style kwargs tools unchanged otherwise; unknown fields were already rejected client-side unless `strict=false` (behavior from an earlier release, verified live this cycle).
- Regenerated tool-schemas.yaml + README.md + README.ko.md after the sync (commit 3faf6b7): tool-schemas.yaml now covers all 307 tools, README Access Lists category 5→6, new "Other" category (2 tools). Drift check exits 0.
- Updated hardcoded unit-test guardrails to the new surface (test_health/test_toolsets): 307 tools, read=139, standard=260, full=307; full pytest suite green (440 passed) — these were missed by the sync task and failed the first CI validate run.
- Verified at commit 4e60684 against the isolated test stack with a local image pinned to that exact SHA (npg-test-mcp @ 127.0.0.1:8082, NPG @ 192.168.0.140): all 3 new tools + `dns_entry_settings` kwargs + access-list hostname flows pass live, error paths match documented codes, regression sample clean, 307/307 tools registered in FastMCP (0 dupes, 0 non-NPG), tier counts pass the pipeline check (read=139, standard=260, full=307), doc drift check exit 0.

### What's new
- New tool `npg_get_dns_entries` — DNS entry overview per settings/env switches, apply state, and entries.
- New tool `npg_apply_dns_entries` — applies pending DNS entries (returns `outcome=accepted`).
- New tool `npg_confirm_access_list_dns` — confirms access-list DNS after review (404 missing list / 400 not a domain / 400 not awaiting review all match documented behavior).
- New capability: DNS entry settings management (entry limit + status) via `npg_update_system_settings` `dns_entry_settings`.
- New capability: access-list rules now support `kind=hostname` DDNS name entries in `npg_create_access_list` / `npg_update_access_list`, and `npg_get_access_list` shows DNS entry status.

### Breaking changes
- (none)

## [0.5.44] - 2026-10-14

### What changed
- `npg_download_log_file` now enforces a 256 KB size cap on raw log downloads (commit 41a44a0): oversized files return the first 262144 bytes plus `truncated`/`total_bytes`/`returned_bytes` metadata and a hint pointing at `npg_view_log_file`, instead of streaming a multi-megabyte body through the MCP wire. Untruncated small downloads behave as before.
- MCP-side `limit`/`offset` pagination was extended to the 10 remaining unpaginated list tools — `npg_list_waf_rules`, `npg_list_exploit_rules`, `npg_list_users`, `npg_list_roles`, `npg_list_sso_providers`, `npg_list_api_tokens`, `npg_list_notification_channels`, `npg_list_cloud_providers`, `npg_list_uri_blocks`, `npg_list_proxy_host_groups` (commit 363d63f). These tools now return explicit paging metadata (`applied`, `unit`, `offset`, `total`, `returned`) so agents can page deterministically instead of pasting entire tables into context.
- Trimmed 12 oversized tool descriptions to ≤398 chars (commit 3ab206c): the 8 planned tools plus 4 further offenders found post-0.5.43. Descriptions were rewritten, not shortened for its own sake — required params, side effects, and next-step hints were preserved within the length budget.
- Verified at commit 3ab206c against the isolated test stack with a local image pinned to that exact SHA: 304 tools / 0 duplicates, all 12 trimmed descriptions served live at ≤398 chars over the MCP wire, doc drift check exit 0, description-param check clean across all 304 tools, 12/12 body-construction checks pass, 440 pytest tests pass, and a live regression sweep (list/download/pagination/dashboard/logs/users) all PASS — including the new 256 KB download cap (truncated:true, 641104 total, 262144 returned).

### What's new
- New capability: 256 KB download cap with truncation metadata on `npg_download_log_file` — protects MCP clients from oversized raw access-log payloads.
- New capability: explicit MCP-side paging on 10 additional list tools (limit/offset + paging metadata).

### Breaking changes
- (none)

## [0.5.43] - 2026-10-12

### What changed
- Synced `swagger.yaml` to upstream NPG v2.61.1 (commit dbb6a9a): 145 insertions / 16 deletions covering validation annotations and docs only — no route, method, or schema changes, so no tool surface impact. The one v2.61.1 behavioral change (POST /api/v1/logs validation 500→400 on invalid values, upstream #325) was already reflected in the `npg_post_log` description shipped in v0.5.42.
- Verified at commit dbb6a9a against the isolated test stack (recreated npg-test-mcp from local image pinned to that SHA): 304 tools / no duplicates, live MCP wire surface check passed, `npg_post_log` 400-contract confirmed live (invalid log_type → local validation error; valid → created; test-stack audit log shows upstream 400), 5-tool regression sample all success, pytest 417 passed, doc-drift and tier checks green.

### What's new
- Nothing — docs-only swagger sync.

### Breaking changes
- (none)

## [0.5.42] - 2026-10-11

### What changed
- `npg_post_log` description updated for upstream NPG v2.61.1 (issue #325): invalid log values (bad log_type enum, status_code outside 100-599, client_ip not a single address, host >500 chars, geo_country_code >2 chars, exploit_rule >50 chars, NUL in any string) now return upstream HTTP 400 naming the field, instead of 500. Description-only change — no signature change, no tool count change.

### What's new
- Nothing — cosmetic description sync with upstream v2.61.1.

### Breaking changes
- None.

## [0.5.41] - 2026-10-11

### What changed
- Synced the MCP wrapper with upstream NPG v2.61.0 (commit 9b85230): added 6 log-lifecycle tools, added `location`/`limit`/`offset` params to the 4 log-file tools, and exposed the `raw_log_archive` settings group through `npg_update_system_settings`'s kwargs whitelist (new field in `upstream_models.py`).
- Extended the 4 raw log-file tools (commits in 9b85230): `npg_list_log_files` gained optional `location` ('local' default or 'archive') / `limit` (1-1000) / `offset` params; `npg_view_log_file`, `npg_download_log_file`, and `npg_delete_log_file` gained optional `location`; descriptions updated with upstream behavior (409 when archive not mounted, raw-name-only 400, 504 on >60s reads, rotation skip reasons).
- Synced `swagger.yaml` to upstream v2.61.0 (commit 9b85230, ~900-line delta) and to intermediate v2.60.1 (commit e2b6103) — docs-only, no tool-surface impact from the swagger changes themselves.
- Tier counts updated for the 6 new tools in the same commit (read=138, standard=257, full=304); `--check-env` tier verification passes.

### What's new
- New tool `npg_check_log_archive`: CHECK the raw log archive directory (mounted, filesystem type, marker-file state).
- New tool `npg_init_log_archive`: INITIALISE the archive directory for this install (write test + marker file).
- New tool `npg_run_log_archive`: MOVE settled rotated raw logs to the archive now (async, answers at once).
- New tool `npg_get_raw_log_reclaim`: GET the status of the raw log reclaim job (DB-side raw-log copy removal).
- New tool `npg_start_raw_log_reclaim`: START (or resume) the reclaim job — DESTRUCTIVE and irreversible for the DB copy.
- New tool `npg_stop_raw_log_reclaim`: PAUSE the reclaim job (cancels in-flight statement, records 'paused').

### Breaking changes
- (none) — all 6 tools are new, the log-file tool params are optional (`None` sends nothing), and settings kwargs were extended additively.

## [0.5.40] - 2026-10-09

### What changed
- Added `npg_probe_upstream` (commit f18b108): a fast, upstream-only connectivity probe wrapping `POST /api/v1/test/proxy-host/{id}` that checks whether the origin server is reachable without running the full end-to-end test chain. It returns a structured error-as-data result (not an exception) when the upstream is dead, so agents can distinguish "backend down" from "tool broken". Signature and description shipped together in the same commit (CI description-sync gate honored).
- Clarified `npg_test_proxy_host` semantics (commit f18b108): its description now explicitly frames the full e2e test vs the fast upstream-only probe, so callers pick the right diagnostic tool.
- Enriched 50 thin tool descriptions (commit c381740): the <60-char no-arg GETs now carry return-shape, workflow pointers, and DESTRUCTIVE/safety warnings — description-only change, no signature changes, verified in sync by the CI drift gate.
- Exposed swagger-supported pagination on 2 list tools (commit 4320591): `npg_list_dns_providers` and `npg_get_certificate_history` gained a `page` param (`int | None = None`, None sends nothing so behavior is byte-identical before/after), matching upstream NPG v2.60.0 swagger for pagination parity.

### What's new
- New tool `npg_probe_upstream(host_id)`: fast upstream-only connectivity probe (upstream NPG's lightweight `POST /test/proxy-host/{id}` path vs the full e2e `npg_test_proxy_host`). Tier counts updated in the same commit (read=136, standard=251, full=298); `--check-env` verification passes.

### Breaking changes
- (none)

## [0.5.39] - 2026-10-09

### What changed
- Fixed `npg_post_log`: the tool sent phantom request fields (`level`, `message`, `source`, `component`) that upstream NPG's `CreateLog` model silently discards, so logged data was silently lost. It now sends the real upstream `CreateLog` fields (`message`, `severity`, `error_message`, plus the `rule_*` / `access` match fields), and `log_type` (`debug`|`info`|`warning`|`error`|`critical`) is enum-validated locally before any API call — empty or out-of-enum values are rejected by the wrapper instead of producing an opaque upstream error. Signature and description changed together in commit `d1a70b6` (CI description-sync gate honored); full verification against the test stack with fresh `verify-*` data across all 3 `log_type` paths confirmed the fields now persist on read-back, and a 5-tool regression sweep passed (verify task `t_6b53aad9`).
- Synced `swagger.yaml` to upstream NPG v2.60.0 (commit `f1ff5b4`): docs-only delta (0 path/schema/method changes; upstream fixes are API-internal), so tool signatures are unchanged.

### What's new
- (none) — no new tools; the tool surface stays at 297 tools with tier counts unchanged (136 read / 250 standard / 297 full).

### Breaking changes
- `npg_post_log` parameter surface changed: the phantom `level` / `source` / `component` params are gone from the schema. Callers should pass `message` + `severity` (+ optional `error_message` and `rule_*` / `access` fields); `log_type` now only accepts the upstream enum.

## [0.5.38] - 2026-10-02

### What changed
- Trimmed 6 oversized tool descriptions to fit the 460-char CI description band (289-388 chars each): `npg_match_filter_subscriptions`, `npg_import_proxy_host`, `npg_get_logs`, `npg_update_proxy_host`, `npg_bulk_get_proxy_host_full`, `npg_update_global_fail2ban` (commit 27a53bb). Required-parameter mentions, enum lists and DESTRUCTIVE/semantic notes were preserved; only the prose padding was cut.
- `npg_update_global_fail2ban` description was stale in a sixth place: it still claimed a `ban_history` mode that the tool's signature does not carry — removed along with the trim.

### What's new
- New tool `npg_match_filter_subscriptions(ip, user_agent)` wrapping `GET /api/v1/filter-subscriptions/match` (upstream NPG v2.59.0, PR #230) (commit e30a9f3). Checks one IP and/or one user-agent against every enabled filter subscription. Both params default to `''`; passing both empty is rejected locally before any API call; an invalid IP passes through (upstream 400 with its own descriptive message). The response separates `ip_matches` / `user_agent_matches`, with `matched_value` and `reason` surfaced per match. Tier: read-level (tier counts 136/250/297).

### Breaking changes
- (none)

## [0.5.37] - 2026-10-02

### What changed
- Corrected stale `NPG_TOOL_LEVEL` tier counts in `.env.example` (135/248/295 → 136/249/296) to match `tier_allowed()` after the v0.5.36 tool addition (commit d3c1277). Until this landed, the `--check-env` tier verification reported a mismatch even though the tests and generated docs were already consistent.

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.36] - 2026-09-27

### What changed
- Synced the wrapper with upstream NPG v2.59.0 (commit cf6450c): refreshed `swagger.yaml` to the upstream v2.59.0 tag (delta from v2.58.0 is exactly +1 operation) and raised the tool-surface guardrails in `tests/test_health.py` / `tests/test_toolsets.py` to 296 tools with the derived `NPG_TOOL_LEVEL` tier counts (read 136 / standard 249 / full 296).
- Regenerated the three generated doc artifacts — `tool-schemas.yaml`, `README.md`, `README.ko.md` — so the new tool is documented, and corrected the stale `NPG_TOOL_LEVEL` tier counts in the README prose (commit 1a85a06). Until this landed, the publish workflow's "Check documentation drift" validate job failed (`tool-schemas.yaml missing 1 tools: ['npg_get_waf_event_rules']`, README.md and README.ko.md totals 295 vs 296), which would have made the release push produce no tag, no GitHub release and no GHCR image.
- Release verified at `1a85a06` against the test stack only (npg-test-mcp @ 127.0.0.1:8082), using a local image built from the workspace HEAD commit and confirmed byte-identical to it (`main.py` sha256 `4db5bdae…`, `client.py` sha256 `048ae0c4…`, container image ID `sha256:2eabfef3…`): 401 pytest passed, AST parse clean, 296 tools registered with 0 duplicate names, `regenerate_all_docs.py --check` exit 0, the new tool reachable over the real MCP wire path, and 3 unrelated read tools (`npg_get_health`, `npg_list_proxy_hosts`, `npg_get_waf_global_rules`) unaffected on NPG 2.59.0. Upstream NPG was not touched.

### What's new
- New tool `npg_get_waf_event_rules` (GET /api/v1/waf/events/{logId}/rules, upstream #306): returns the WAF rule(s) that contributed to one specific security event. REQUIRED: `log_id` (the event id) and `at` (the event timestamp) — `at` selects the TimescaleDB chunk the event lives in, so an out-of-chunk timestamp returns upstream 404 "WAF event not found"; empty `log_id`/`at` are rejected locally before any API call. Verified live against a genuine SQL-injection event injected on the disposable test stack: the call returned the owning `proxy_host_id` plus `rules[]` (rule_id 942100, message, severity, category, `excluded`).

### Breaking changes
- (none)

## [0.5.35] - 2026-09-25

### What changed
- `npg_update_proxy_host` description trimmed from 624 to 451 chars to fit the 460-char CI description band, preserving the `host_id` REQUIRED mention, tags tri-state semantics, the `waf_mode` only-applies-when-`waf_use_global=false` gate, and nullable-id `''`-clears behavior (commit 32ef397).
- README prose tier counts updated from 134/247/294 to 135/248/295 to reflect the two new tools added in this release (commit a5fc983).
- Ruff W292 trailing-newline lint fix in tests; no behavior change (commit e8fd45e).
- Release verified against the test stack (npg-test-mcp @ 127.0.0.1:8082, local image built from workspace HEAD): 17/17 live checks passed — served description confirmed at 451 chars with all safety semantics, `npg_get_health` healthy, bulk enable/disable round-trips on a throwaway host, tags replace/clear verified via GET, 4 unrelated read tools unaffected; static checks: 401 pytest passed, ruff clean, docs drift check in sync, 295 tools registered with 0 duplicates, container package sha256s identical to workspace HEAD.

### What's new
- New tool `npg_get_health` (GET /api/v1/health): origin-root liveness probe returning overall health status plus per-dependency (db, cache) detail — commit 629db40.
- New tool `npg_bulk_set_proxy_hosts_enabled` (POST /api/v1/proxy-hosts/bulk-enabled): batch enable/disable up to 50 hosts per call with dedupe, per-entry error isolation, and an optional `skip_nginx` query param mirroring `npg_update_proxy_host` — commit 5f82041.

### Breaking changes
- (none)

## [0.5.34] - 2026-09-23

### What changed
- Exposed upstream time-window and filter parameters on 12 read/diagnostic tools (commit 72cdf64), all None-defaulted so zero-arg calls send no params and behave byte-identically to before: `npg_get_dashboard_geoip_stats` (hours), `npg_get_dashboard_health_history` (hours, limit), `npg_get_dashboard_stats` (start, end, proxy_host_id), `npg_get_expiring_certificates` (days), `npg_get_log_stats` (log_type, host, client_ip, start_time, end_time, proxy_host_id, block_reason, search — note the API defaults the stats window to the last 24h without an explicit start/end), `npg_get_ban_history` (ip_address, event_type, source, proxy_host_id, start_date, end_date, page, limit), `npg_get_ban_history_for_ip` (page, limit), `npg_get_waf_global_history` (limit), `npg_get_waf_host_history` (limit), `npg_list_audit_logs` (offset, search, user_id, start_time, end_time), and `npg_list_system_logs` (container, component, search, start_time, end_time, offset). Blank-string filters are dropped rather than sent. All tool descriptions rewritten in the same commit per the signature⇒description rule.
- Added 331 lines of body-construction tests (`tests/test_list_pagination.py`): zero-arg sends no params, verbatim time-window forwarding, filter mapping, blank-string suppression, and negative-number clean-error coverage for the 12 changed tools. Ruff lint fixes for the mutation-query-param tests (commit e9f303c, no behavior change).
- Verified against the test stack (npg-test-mcp @ 127.0.0.1:8082, image local/npg-mcp:72cdf64 built from the workspace checkout and confirmed equal to container image ID): 385/385 pytest passed, 293 tools registered / 0 duplicates, ruff clean, docs drift check exit 0, all 12 changed tools param-exercised live plus 43 regression tools; test stack pinned back to the published image afterwards (pristine, prod untouched).

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.33] - 2026-09-23

### What changed
- Exposed upstream mutation side-effect controls (commit ab604de): `skip_reload` on the 5 sub-config mutators (`npg_update_proxy_host_bot_filter`, `npg_update_proxy_host_uri_block`, `npg_update_proxy_host_cloud_blocking`, `npg_create_proxy_host_geo`, `npg_delete_proxy_host_geo`), `ddns_remove_provider` on `npg_update_proxy_host`, and a `remove_provider` opt-out on `npg_delete_ddns_record`. All default to current behavior, so existing callers are unaffected. Verified against the test stack (npg-test-mcp @ 127.0.0.1:8082, image local/npg-mcp:ab604de matching workspace commit): 352/352 pytest green (19 new mutation-param tests), 293 tools / 0 duplicates, live round-trips for all 5 skip_reload mutators plus both DDNS delete modes, throwaway host cleaned up.
- `npg_get_logs` now exposes the upstream `/logs` keyset cursor plus 32 upstream filters (commit 73f06dd): `log_type`, time range, severity, `block_reason`, `bot_category`, `rule_id`, and more — full parity with the upstream logs API instead of just page/limit.
- Added `page`/`per_page` plus upstream filters to the 9 zero-arg list tools (commit 39cb315): `npg_list_certificates`, `npg_list_banned_ips`, and friends now support server-side pagination, search, status/provider filters, and sorting instead of always returning the full unpaginated set.
- Description trim pass (commit e8b1d2f): 8 oversized tool descriptions (670/669/650/618/584/550/456/451 chars) cut under the 400–460 band, preserving REQUIRED params and enum hints. No signature changes.
- swagger.yaml synced to upstream v2.58.0 (commit d621d6a, local-only reference file). Tier-count docs corrected to match `tier_allowed()` — 134/246/293 (commit b4df8bf).

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.32] - 2026-09-20

### What changed
- Upstream v2.57.0 sync (commit 5c94e0e): `npg_list_proxy_hosts` now supports filtering by `tags`, `domain`, `upstream`, and `enabled` — `domain` matches the parent-domain bucket (a full subdomain value returns nothing by design), and tag filters combine with AND semantics. `npg_create_proxy_host` and `npg_update_proxy_host` accept a `tags` list (create replaces with sent tags; update fully replaces the stored set).
- Documentation pass on the new filters (commit a988761): clarified `domain`/`upstream` filter semantics directly in the `npg_list_proxy_hosts` description so agents don't misinterpret subdomain filtering.
- Test hygiene (commit 101decf): ruff W292 trailing-newline fix in the tag tests; no behavior change.
- swagger.yaml updated to upstream v2.57.0 (commit 7f49510, local-only reference file). Verified against the test stack on a locally built image matching workspace HEAD (local/npg-mcp:7f49510): 293/293 pytest passed, 293 tools registered with no duplicates, docs drift check clean, live create/update/tag-filter/groups round-trips with disposable hosts all passed.

### What's new
- New tool `npg_list_proxy_host_groups` (GET /api/v1/proxy-hosts/groups): returns host counts grouped by tag, domain, and upstream, and mirrors the enabled/disabled status split — cross-checkable against the new list filters.

### Breaking changes
- (none)

## [0.5.31] - 2026-09-19

### What changed
- Removed phantom `host_header` and `extra_domains` parameters from `npg_create_proxy_host` and `npg_update_proxy_host` (commit f7801da): the fields were accepted by the tools and mapped to a body key `pass_host_header`, but the upstream `CreateProxyHostRequest`/`UpdateProxyHostRequest` models do not define them, so Go silently ignored them — callers got `success: true` with nothing applied. Also dropped the phantom `extra_domains` optional CSV column from `npg_bulk_import_proxy_hosts` (it fed the removed create param). Verified against a locally-built image (local/npg-mcp:f7801da) on the test stack: phantom fields absent from signatures, tool-schemas.yaml, and the served MCP surface (292/292 tools, 0 dupes); create/get/update/bulk-import round-trips clean; extra_domains CSV column now ignored; 0 param mismatches across all 292 tools; 283 tests pass; all verify- fixtures cleaned up.
- `scripts/regenerate_all_docs.py` now parses multi-line `def` signatures (commit f7801da): tool-schemas.yaml had drifted because signature lines spanning multiple lines were only partially parsed, inflating the diff. Docs verified in sync (drift check exit 0).

### What's new
- (none)

### Breaking changes
- `npg_create_proxy_host` and `npg_update_proxy_host` no longer accept `host_header` or `extra_domains` parameters, and `npg_bulk_import_proxy_hosts` no longer accepts an `extra_domains` CSV column. The parameters were phantom (silently ignored by the NPG API), so no behavior is lost — callers passing them will now get a Pydantic validation error instead of a silent no-op.

## [0.5.30] - 2026-09-19

### What changed
- `npg_bulk_get_proxy_host_full` now dedupes incoming `host_ids` on the URL-encoded `_id_path` form (commit 13302f3): since the percent-encoding change in 0.5.29 (commit c40c1b5), the dedupe key had regressed to the raw `_id_str` form while section URLs are interpolated with `_id_path` — a no-op for UUIDs (quote-invariant) but an encoding-contract deviation that could double-fetch for ids needing encoding. The fix matches the single-host tool `npg_get_proxy_host_full`, and response keys still echo the caller's raw spelling via `_id_str`. Verified with 2 new regression tests (283 passed) and live MCP calls against the test stack (dedupe, sections filter, nonexistent-id isolation into `hosts_failed`).
- `npg_get_certificate_history` description rewritten from a 24-char stub to a workflow-aware GET description (commit 13302f3): explains it returns cert history events after issuance, suggests `npg_get_expiring_certificates` for expiry tracking, and notes an empty result is normal. No signature change.

### What's new
- Regression-test coverage for the bulk full-fetch encoding contract (dedupe key + response-key pinning) in `tests/test_bulk_concurrency.py` (281 → 283 tests).

### Breaking changes
- (none)

## [0.5.29] - 2026-09-17

### What changed
- Percent-encode path-interpolated identifiers (commit c40c1b5): `_id_path()` now returns `quote(str(id), safe="")`, so URL-unsafe characters in ids/slugs (spaces, slashes, `%`, etc.) can never alter the URL path structure of API calls. Added `_id_str` for identifiers embedded in raw request/response body values. Verified against the test stack with a local image build of the release commit: 281 unit tests pass (incl. 25 new encoding tests), ruff + mypy clean, doc drift check exit 0, and 9 read-only tools regressed successfully over the live MCP protocol.
- Capped concurrent NPG API calls in bulk fan-out (commit 3be533a): added the `_gather_bounded(limit, coros)` order-preserving helper and rewired bulk tools (e.g. `npg_bulk_apply_certificate`, cap 8) to use it, preventing request floods against the NPG API that triggered upstream rate limiting and connection failures during bulk operations.
- Enforced repo-wide lint in CI (commit 825eda5): fixed all 74 ruff findings in `tests/` (62 E501 line-length rewraps with zero test-logic changes plus 12 auto-fixable I001/W292/F401) and added a lint gate to the publish.yml validate job so future lint regressions block publishing.
- Synced swagger.yaml to upstream NPG v2.56.0 (commit b067212) to keep the local API reference current.

### What's new
- `_id_str` helper for stringifying identifiers in raw body values, complementing the URL-path percent-encoding of `_id_path` (commit c40c1b5).
- `_gather_bounded` bounded-concurrency helper used by all bulk fan-out tools (commit 3be533a).

### Breaking changes
- (none)

## [0.5.28] - 2026-09-12

### What changed
- `npg_update_proxy_host` now accepts `waf_mode` (`detection`|`blocking`). The parameter was missing from the tool signature and body map entirely, so per-host WAF mode changes silently no-op'd — the tool returned `success: true` while the API never received the field. Note the upstream contract: per-host `waf_mode` is only consulted when `waf_use_global=false`; while a host inherits the global WAF, the API ignores a per-host mode by design. Description updated to document this in the same commit (CI description-sync gate).

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.27] - 2026-09-10

### What changed
- `npg_create_proxy_host` and `npg_update_proxy_host` now coerce integer `ssl_cert_id` values to strings before sending them to the NPG API (commit 514e3a7). Previously an int cert id was serialized as a raw JSON int, so the API received `certificate_id: 12345` and rejected the request with a Postgres UUID parse error (`invalid input syntax for type uuid: "12345"`) instead of accepting the numeric certificate id. The fix adds `ssl_cert_id` to the `_build_body` `id_fields` set, so id-typed fields are stringified the same way `_id_path()` handles URL ids. Verified live on the isolated test stack with verify- prefixed data: int cert ids now reach the API as strings, string UUID round-trips are preserved, and a max-int (2^63) coerces without crashing.
- Corrected stale tool-tier counts in `.env.example` comments (commit 267b9f4): documented counts 132/241/288 no longer matched the tool surface after recent additions — comments updated to 133/245/292 to reflect the actual distribution.
- Fixed a ruff I001 import-sort violation in `npg_mcp/main.py` (commit da4436c) so lint stays clean in CI.

### What's new
- (none)

### Breaking changes
- (none)

## [0.5.26] - 2026-09-08
# Changelog

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
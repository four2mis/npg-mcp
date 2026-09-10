# Changelog

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
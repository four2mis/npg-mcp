"""Unit tests for npg_bulk_import_proxy_hosts.

Verifies, without any network access (recording fake client):
* CSV parsing: required columns enforced, header-only payload rejected,
  quoted multi-domain cells split into lists,
* each row routes through npg_create_proxy_host's real code path (the exact
  POST body carries mapped API field names — certificate_id, ssl_force_https,
  block_normal_access — plus the tool's hardcoded defaults),
* per-row aggregation: one bad row (bad bool cell, missing domain, bad port)
  fails only its row; valid rows still import,
* the 50-row bulk cap raises ValueError before any call,
* empty csv_data is rejected,
* skip_nginx=false issues exactly one POST /api/v1/proxy-hosts/sync at the
  end when at least one row succeeded; default true never syncs,
* dry-run payloads from the client surface as {dry_run: ...} entries and
  don't count as created.

Monkeypatches npg_mcp.main._get_client with a recording fake so the tools'
real code paths run end to end.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod
from npg_mcp.main import _BULK_HOST_LIMIT


class _RecordingClient:
    """Fake NPGClient recording every (method, path, body) call."""

    def __init__(self):
        self.calls = []

    def post(self, path, body=None, params=None):
        self.calls.append(("POST", path, body, params))
        return {"created": True}

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        return {"updated": True}

    def get(self, path, params=None):
        self.calls.append(("GET", path, None, params))
        return []


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _csv(*lines: str) -> str:
    return "\n".join(lines) + "\n"


HEADER = "domain_names,forward_host,forward_port"
GOOD_ROW = "app.example.com,10.0.0.10,8080"


class TestCsvParsing:
    def test_missing_required_column_rejected_before_any_call(self, recording):
        result = _run(main_mod.npg_bulk_import_proxy_hosts(
            csv_data="domain_names,forward_host\napp.example.com,10.0.0.1\n"))
        assert result["success"] is False
        assert "forward_port" in result["error"]
        assert recording.calls == []

    def test_header_only_payload_rejected(self, recording):
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=HEADER + "\n"))
        # Zero rows -> success with an empty summary (nothing to do).
        assert result["success"] is True
        assert result["summary"] == {"rows": 0, "created": 0, "failed": 0}
        assert recording.calls == []

    def test_empty_csv_data_rejected(self):
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=""))
        assert result["success"] is False
        assert "csv_data is required" in result["error"]

    def test_quoted_multi_domain_cell_splits(self, recording):
        result = _run(main_mod.npg_bulk_import_proxy_hosts(
            csv_data=_csv(HEADER, '"app.example.com,api.example.com",10.0.0.10,8080')))
        assert result["success"] is True
        post_calls = [c for c in recording.calls if c[0] == "POST" and c[1].endswith("proxy-hosts")]
        assert len(post_calls) == 1
        assert post_calls[0][2]["domain_names"] == ["app.example.com", "api.example.com"]


class TestRowImport:
    def test_row_routes_through_create_with_mapped_fields(self, recording):
        csv_data = _csv(
            HEADER + ",ssl_cert_id,ssl_forced,block_normal,waf_paranoia_level",
            "app.example.com,10.0.0.10,8080,cert-uuid-1,false,true,3",
        )
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=csv_data))
        assert result["success"] is True
        assert result["summary"] == {"rows": 1, "created": 1, "failed": 0}
        post_calls = [c for c in recording.calls if c[0] == "POST" and c[1].endswith("proxy-hosts")]
        body = post_calls[0][2]
        # MCP param names map to API field names via npg_create_proxy_host.
        assert body["certificate_id"] == "cert-uuid-1"
        assert body["ssl_force_https"] is False
        assert body["block_normal_access"] is True
        assert body["waf_paranoia_level"] == 3
        # Hardcoded defaults of the create tool are present.
        assert body["proxy_type"] == "http"
        assert body["enabled"] is True

    def test_one_bad_row_does_not_abort_batch(self, recording):
        csv_data = _csv(
            HEADER + ",ssl_enabled",
            f"{GOOD_ROW},true",
            "bad.example.com,10.0.0.11,80,ture",     # bad bool cell -> row error
            "blog.example.org,10.0.0.12,80,",        # empty optional cell -> fine
        )
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=csv_data))
        assert result["success"] is True
        assert result["summary"]["rows"] == 3
        assert result["summary"]["created"] == 2
        assert result["summary"]["failed"] == 1
        assert result["data"][1]["success"] is False
        assert "expected true/false" in result["data"][1]["error"]

    def test_missing_domain_fails_only_that_row(self, recording):
        csv_data = _csv(
            HEADER,
            GOOD_ROW,
            ",10.0.0.99,80",
        )
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=csv_data))
        assert result["success"] is True
        assert result["summary"]["created"] == 1
        assert result["summary"]["failed"] == 1
        assert "domain_names is required" in result["data"][1]["error"]

    def test_bad_port_fails_only_that_row(self, recording):
        csv_data = _csv(
            HEADER,
            GOOD_ROW,
            "oops.example.com,10.0.0.99,not-a-port",
        )
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=csv_data))
        assert result["success"] is True
        assert result["summary"]["failed"] == 1
        assert result["data"][1]["success"] is False

    def test_unknown_column_fails_only_its_row(self, recording):
        csv_data = _csv(
            HEADER + ",bogus_setting",
            f"{GOOD_ROW},whatever",
        )
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=csv_data))
        # Unknown columns are simply ignored cells — they are not create-tool
        # kwargs, but they must not crash or fail the row either: DictReader
        # keeps them in the row dict and the column loop skips them.
        assert result["success"] is True
        assert result["summary"]["created"] == 1

    def test_cap_raises_value_error_before_any_call(self, recording):
        rows = "\n".join(f"h{i}.example.com,10.0.0.1,80" for i in range(_BULK_HOST_LIMIT + 1))
        csv_data = _csv(HEADER, rows)
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=csv_data))
        assert result["success"] is False
        assert f"exceeds the limit of {_BULK_HOST_LIMIT}" in result["error"]
        assert recording.calls == []

    def test_at_cap_is_allowed(self, recording):
        rows = "\n".join(f"h{i}.example.com,10.0.0.1,80" for i in range(_BULK_HOST_LIMIT))
        csv_data = _csv(HEADER, rows)
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=csv_data))
        assert result["success"] is True
        assert result["summary"]["created"] == _BULK_HOST_LIMIT


class TestSyncBehavior:
    def test_default_skip_nginx_never_syncs(self, recording):
        result = _run(main_mod.npg_bulk_import_proxy_hosts(csv_data=_csv(HEADER, GOOD_ROW)))
        assert result["success"] is True
        assert result["sync"] is None
        syncs = [c for c in recording.calls if c[1] == "/api/v1/proxy-hosts/sync"]
        assert syncs == []

    def test_skip_nginx_false_syncs_once_after_rows(self, recording):
        result = _run(main_mod.npg_bulk_import_proxy_hosts(
            csv_data=_csv(HEADER, GOOD_ROW), skip_nginx=False))
        assert result["success"] is True
        syncs = [c for c in recording.calls if c[1] == "/api/v1/proxy-hosts/sync"]
        assert len(syncs) == 1
        assert recording.calls[-1][1] == "/api/v1/proxy-hosts/sync"

    def test_no_sync_when_all_rows_failed_even_with_skip_false(self, recording):
        result = _run(main_mod.npg_bulk_import_proxy_hosts(
            csv_data=_csv(HEADER, ",10.0.0.1,80"), skip_nginx=False))
        assert result["success"] is True
        assert result["summary"]["failed"] == 1
        syncs = [c for c in recording.calls if c[1] == "/api/v1/proxy-hosts/sync"]
        assert syncs == []


class TestDryRunSurfacing:
    def test_dry_run_payload_surfaced_per_row_not_counted_as_created(self, monkeypatch):
        class _DryRunClient(_RecordingClient):
            def post(self, path, body=None, params=None):
                self.calls.append(("POST", path, body, params))
                if path.endswith("/sync"):
                    return {"synced": True}
                return {"dry_run": True, "method": "POST", "path": path, "body": body}

        client = _DryRunClient()
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        result = _run(main_mod.npg_bulk_import_proxy_hosts(
            csv_data=_csv(HEADER, GOOD_ROW), skip_nginx=False))
        assert result["success"] is True
        entry = result["data"][0]
        assert entry["success"] is True
        dry = entry["result"]["dry_run"]
        assert dry["method"] == "POST"
        # Nothing was actually created, so no trailing sync fires.
        syncs = [c for c in client.calls if c[1] == "/api/v1/proxy-hosts/sync"]
        assert syncs == []

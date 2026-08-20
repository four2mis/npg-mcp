"""Unit tests for pagination/filter query params on the 4 list tools.

Covers, without any network access (recording fake client):
* npg_list_proxy_hosts  — page/limit/search params on GET /api/v1/proxy-hosts
* npg_get_logs          — host/status/method/limit/offset params on GET /api/v1/logs
* npg_list_audit_logs   — page/limit/action/resource_type on GET /api/v1/audit-logs
* npg_list_system_logs  — source/level/limit on GET /api/v1/system-logs
* conditional param building: only provided values appear in the query string
* zero-arg regression: calls stay identical to the pre-change behavior (no params)
* invalid ints (negative limit/offset/page/status) surface as clean
  {"success": False, "error": ...} dicts, not HTTP 500s.

Monkeypatches npg_mcp.main._get_client with a recording fake so the tools'
real code paths run end to end (validation -> param build -> HTTP call shape).
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod
from npg_mcp.main import _list_params, _validate_query_int


class _RecordingClient:
    """Fake NPGClient that records every (method, path, params) GET call."""

    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        return {"data": [], "total": 0}


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


class TestListParamsHelper:
    def test_empty_when_nothing_provided(self):
        assert _list_params(None) == {}
        assert _list_params(None, None, None) == {}

    def test_only_provided_values_sent(self):
        assert _list_params(limit=5) == {"limit": 5}
        assert _list_params(limit=5, page=2) == {"limit": 5, "page": 2}
        assert _list_params(limit=10, offset=20) == {"limit": 10, "offset": 20}

    def test_negative_values_rejected(self):
        with pytest.raises(ValueError):
            _list_params(limit=-1)
        with pytest.raises(ValueError):
            _list_params(None, offset=-5)
        with pytest.raises(ValueError):
            _list_params(None, None, page=0 - 1)
        with pytest.raises(ValueError):
            _validate_query_int("status", -1)


class TestListProxyHosts:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_proxy_hosts())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/proxy-hosts", None)]

    def test_limit_and_page_sent(self, recording):
        _run(main_mod.npg_list_proxy_hosts(page=2, limit=10))
        assert recording.calls == [("GET", "/api/v1/proxy-hosts", {"page": 2, "limit": 10})]

    def test_search_sent_only_when_nonempty(self, recording):
        _run(main_mod.npg_list_proxy_hosts(search="mcp-test-"))
        assert recording.calls == [("GET", "/api/v1/proxy-hosts", {"search": "mcp-test-"})]
        _run(main_mod.npg_list_proxy_hosts(search="  "))
        assert recording.calls[-1] == ("GET", "/api/v1/proxy-hosts", None)

    def test_negative_limit_clean_error(self, recording):
        result = _run(main_mod.npg_list_proxy_hosts(limit=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestGetLogs:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_logs())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/logs", None)]

    def test_all_filters_sent(self, recording):
        _run(main_mod.npg_get_logs(host="foo.example.com", status=404, method="GET", limit=50, offset=10))
        assert recording.calls == [
            ("GET", "/api/v1/logs", {"host": "foo.example.com", "status": 404, "method": "GET", "limit": 50, "offset": 10})
        ]

    def test_partial_filters(self, recording):
        _run(main_mod.npg_get_logs(status=404, limit=50))
        assert recording.calls == [("GET", "/api/v1/logs", {"status": 404, "limit": 50})]

    def test_negative_status_clean_error(self, recording):
        result = _run(main_mod.npg_get_logs(status=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestListAuditLogs:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_audit_logs())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/audit-logs", None)]

    def test_filters_sent(self, recording):
        _run(main_mod.npg_list_audit_logs(page=1, limit=25, action="create", resource_type="proxy_host"))
        assert recording.calls == [
            ("GET", "/api/v1/audit-logs", {"page": 1, "limit": 25, "action": "create", "resource_type": "proxy_host"})
        ]


class TestListSystemLogs:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_system_logs())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/system-logs", None)]

    def test_filters_sent(self, recording):
        _run(main_mod.npg_list_system_logs(source="nginx", level="error", limit=100))
        assert recording.calls == [("GET", "/api/v1/system-logs", {"source": "nginx", "level": "error", "limit": 100})]

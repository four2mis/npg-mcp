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
from npg_mcp.main import _list_params, _list_params_per_page, _validate_query_int


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


class TestListParamsPerPageHelper:
    def test_maps_limit_to_per_page(self):
        assert _list_params_per_page(limit=1) == {"per_page": 1}
        assert _list_params_per_page(limit=5, page=2) == {"per_page": 5, "page": 2}

    def test_offset_to_page(self):
        # offset 10 with page size 5 -> page 3
        assert _list_params_per_page(limit=5, offset=10) == {"per_page": 5, "page": 3}
        # default page size 50 when limit omitted
        assert _list_params_per_page(offset=50) == {"page": 2}

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            _list_params_per_page(limit=-1)
        with pytest.raises(ValueError):
            _list_params_per_page(offset=-3)


class TestListProxyHosts:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_proxy_hosts())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/proxy-hosts", None)]

    def test_limit_and_page_sent(self, recording):
        _run(main_mod.npg_list_proxy_hosts(page=2, limit=10))
        assert recording.calls == [
            ("GET", "/api/v1/proxy-hosts", {"page": 2, "per_page": 10})
        ]

    def test_search_sent_only_when_nonempty(self, recording):
        _run(main_mod.npg_list_proxy_hosts(search="mcp-test-"))
        assert recording.calls == [
            ("GET", "/api/v1/proxy-hosts", {"search": "mcp-test-"})
        ]
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
        _run(
            main_mod.npg_get_logs(
                host="foo.example.com", status=404, method="GET", limit=50, offset=10
            )
        )
        # limit -> per_page; offset 10 with page size 50 -> page 1;
        # status -> status_code (upstream field name)
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs",
                {
                    "per_page": 50,
                    "page": 1,
                    "host": "foo.example.com",
                    "status_code": 404,
                    "method": "GET",
                },
            )
        ]

    def test_partial_filters(self, recording):
        _run(main_mod.npg_get_logs(status=404, limit=50))
        assert recording.calls == [
            ("GET", "/api/v1/logs", {"per_page": 50, "status_code": 404})
        ]

    def test_negative_status_clean_error(self, recording):
        result = _run(main_mod.npg_get_logs(status=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []

    def test_status_class_filters_sent(self, recording):
        _run(
            main_mod.npg_get_logs(
                status_classes=["4xx"],
                exclude_status_codes=[200, 404],
                exclude_status_classes=["2xx"],
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs",
                {
                    "status_classes": ["4xx"],
                    "exclude_status_codes": [200, 404],
                    "exclude_status_classes": ["2xx"],
                },
            )
        ]

    def test_status_class_filters_combined_with_existing(self, recording):
        _run(
            main_mod.npg_get_logs(
                host="foo.example.com", status_classes=["5xx", "4xx"], limit=50
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs",
                {
                    "per_page": 50,
                    "host": "foo.example.com",
                    "status_classes": ["5xx", "4xx"],
                },
            )
        ]

    def test_empty_status_class_lists_not_sent(self, recording):
        result = _run(
            main_mod.npg_get_logs(
                status_classes=[], exclude_status_codes=[], exclude_status_classes=[]
            )
        )
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/logs", None)]

    # ── Phase-3 batch: cursor + 32 upstream filters ───────────────────────

    def test_cursor_passed_verbatim_replaces_offset(self, recording):
        _run(main_mod.npg_get_logs(cursor="abc123|42", limit=5))
        # cursor replaces the offset->page mapping entirely
        assert recording.calls == [
            ("GET", "/api/v1/logs", {"per_page": 5, "cursor": "abc123|42"})
        ]

    def test_cursor_with_offset_drops_offset(self, recording):
        _run(main_mod.npg_get_logs(cursor="abc123|42", offset=20, limit=5))
        assert recording.calls == [
            ("GET", "/api/v1/logs", {"per_page": 5, "cursor": "abc123|42"})
        ]

    def test_blank_cursor_not_sent(self, recording):
        _run(main_mod.npg_get_logs(cursor="  ", offset=20, limit=5))
        assert recording.calls == [("GET", "/api/v1/logs", {"per_page": 5})]

    def test_log_type_enum_forwarded(self, recording):
        _run(main_mod.npg_get_logs(log_type="modsec"))
        assert recording.calls == [("GET", "/api/v1/logs", {"log_type": "modsec"})]

    def test_time_range_forwarded(self, recording):
        _run(
            main_mod.npg_get_logs(
                start_time="2026-09-20T00:00:00Z", end_time="2026-09-21T00:00:00Z"
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs",
                {
                    "start_time": "2026-09-20T00:00:00Z",
                    "end_time": "2026-09-21T00:00:00Z",
                },
            )
        ]

    def test_multiselect_lists_repeatable(self, recording):
        _run(
            main_mod.npg_get_logs(
                hosts=["a.example.com", "b.example.com"],
                client_ips=["1.1.1.1", "2.2.2.2"],
                uris=["/login"],
                user_agents=["curl"],
                status_codes=[404, 500],
                severity="error",
                block_reason="waf",
                bot_category="bad_bot",
                exploit_rule="SQLI-001",
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs",
                {
                    "hosts": ["a.example.com", "b.example.com"],
                    "client_ips": ["1.1.1.1", "2.2.2.2"],
                    "uris": ["/login"],
                    "user_agents": ["curl"],
                    "status_codes": [404, 500],
                    "severity": "error",
                    "block_reason": "waf",
                    "bot_category": "bad_bot",
                    "exploit_rule": "SQLI-001",
                },
            )
        ]

    def test_scalar_filters_forwarded(self, recording):
        _run(
            main_mod.npg_get_logs(
                client_ip="10.0.0.1",
                uri="/admin",
                user_agent="Mozilla",
                rule_id="942100",
                proxy_host_id="123e4567-e89b-12d3-a456-426614174000",
                geo_country_code="KR",
                search="suspicious",
                min_size=100,
                max_size=5000,
                min_request_time=2,
                upstream_addr="127.0.0.1:8080",
                upstream_status="502, 200",
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs",
                {
                    "client_ip": "10.0.0.1",
                    "uri": "/admin",
                    "user_agent": "Mozilla",
                    "rule_id": "942100",
                    "proxy_host_id": "123e4567-e89b-12d3-a456-426614174000",
                    "geo_country_code": "KR",
                    "search": "suspicious",
                    "min_size": 100,
                    "max_size": 5000,
                    "min_request_time": 2,
                    "upstream_addr": "127.0.0.1:8080",
                    "upstream_status": "502, 200",
                },
            )
        ]

    def test_exclude_lists_forwarded(self, recording):
        _run(
            main_mod.npg_get_logs(
                exclude_ips=["1.2.3.4", "10.0.0.0/8"],
                exclude_user_agents=["bot"],
                exclude_uris=["/health"],
                exclude_hosts=["x.example.com"],
                exclude_countries=["US"],
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs",
                {
                    "exclude_ips": ["1.2.3.4", "10.0.0.0/8"],
                    "exclude_user_agents": ["bot"],
                    "exclude_uris": ["/health"],
                    "exclude_hosts": ["x.example.com"],
                    "exclude_countries": ["US"],
                },
            )
        ]

    def test_sort_params_forwarded(self, recording):
        _run(main_mod.npg_get_logs(sort_by="host", sort_order="asc"))
        assert recording.calls == [
            ("GET", "/api/v1/logs", {"sort_by": "host", "sort_order": "asc"})
        ]

    def test_negative_int_filter_clean_error(self, recording):
        result = _run(main_mod.npg_get_logs(min_size=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []

    def test_new_phase3_filters_zero_arg_still_no_params(self, recording):
        result = _run(main_mod.npg_get_logs())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/logs", None)]


class TestListAuditLogs:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_audit_logs())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/audit-logs", None)]

    def test_filters_sent(self, recording):
        _run(
            main_mod.npg_list_audit_logs(
                page=1, limit=25, action="create", resource_type="proxy_host"
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/audit-logs",
                {
                    "page": 1,
                    "limit": 25,
                    "action": "create",
                    "resource_type": "proxy_host",
                },
            )
        ]


class TestListSystemLogs:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_system_logs())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/system-logs", None)]

    def test_filters_sent(self, recording):
        _run(main_mod.npg_list_system_logs(source="nginx", level="error", limit=100))
        assert recording.calls == [
            (
                "GET",
                "/api/v1/system-logs",
                {"source": "nginx", "level": "error", "limit": 100},
            )
        ]


# ── Phase-2 batch: the 9 zero-arg list tools ─────────────────────────────
# All honor page/per_page directly (limit -> per_page via _list_params_per_page).

CERT_PATH = "/api/v1/certificates"


class TestListCertificates:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_certificates())
        assert result["success"] is True
        assert recording.calls == [("GET", CERT_PATH, None)]

    def test_page_limit_forwarded_as_per_page(self, recording):
        _run(main_mod.npg_list_certificates(page=2, limit=50))
        assert recording.calls == [("GET", CERT_PATH, {"page": 2, "per_page": 50})]

    def test_all_filters_forwarded(self, recording):
        _run(
            main_mod.npg_list_certificates(
                search="example",
                status="issued",
                provider="letsencrypt",
                sort_by="domain",
                sort_order="asc",
            )
        )
        assert recording.calls == [
            (
                "GET",
                CERT_PATH,
                {
                    "search": "example",
                    "status": "issued",
                    "provider": "letsencrypt",
                    "sort_by": "domain",
                    "sort_order": "asc",
                },
            )
        ]

    def test_empty_search_not_sent(self, recording):
        _run(main_mod.npg_list_certificates(search="   "))
        assert recording.calls == [("GET", CERT_PATH, None)]

    def test_negative_page_clean_error(self, recording):
        result = _run(main_mod.npg_list_certificates(page=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestListBannedIps:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_banned_ips())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/banned-ips", None)]

    def test_filter_and_host_forwarded(self, recording):
        _run(
            main_mod.npg_list_banned_ips(
                filter="host", proxy_host_id="abc-uuid", page=1, limit=25
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/banned-ips",
                {
                    "page": 1,
                    "per_page": 25,
                    "filter": "host",
                    "proxy_host_id": "abc-uuid",
                },
            )
        ]

    def test_blank_proxy_host_id_not_sent(self, recording):
        _run(main_mod.npg_list_banned_ips(proxy_host_id="  "))
        assert recording.calls == [("GET", "/api/v1/banned-ips", None)]


class TestSimplePaginationList:
    """page/limit-only tools: backups, redirect hosts, access lists,
    auth providers, ddns records, filter subscriptions."""

    @pytest.mark.parametrize(
        "tool, path",
        [
            ("npg_list_backups", "/api/v1/backups"),
            ("npg_list_redirect_hosts", "/api/v1/redirect-hosts"),
            ("npg_list_access_lists", "/api/v1/access-lists"),
            ("npg_list_auth_providers", "/api/v1/auth-providers"),
            ("npg_list_ddns_records", "/api/v1/ddns-records"),
            ("npg_list_filter_subscriptions", "/api/v1/filter-subscriptions"),
        ],
    )
    def test_zero_arg_sends_no_params(self, recording, tool, path):
        result = _run(getattr(main_mod, tool)())
        assert result["success"] is True
        assert recording.calls == [("GET", path, None)]

    @pytest.mark.parametrize(
        "tool, path",
        [
            ("npg_list_backups", "/api/v1/backups"),
            ("npg_list_redirect_hosts", "/api/v1/redirect-hosts"),
            ("npg_list_access_lists", "/api/v1/access-lists"),
            ("npg_list_auth_providers", "/api/v1/auth-providers"),
            ("npg_list_ddns_records", "/api/v1/ddns-records"),
            ("npg_list_filter_subscriptions", "/api/v1/filter-subscriptions"),
        ],
    )
    def test_page_limit_forwarded_as_per_page(self, recording, tool, path):
        _run(getattr(main_mod, tool)(page=3, limit=10))
        assert recording.calls == [("GET", path, {"page": 3, "per_page": 10})]

    @pytest.mark.parametrize(
        "tool, path",
        [
            ("npg_list_backups", "/api/v1/backups"),
            ("npg_list_redirect_hosts", "/api/v1/redirect-hosts"),
            ("npg_list_access_lists", "/api/v1/access-lists"),
            ("npg_list_auth_providers", "/api/v1/auth-providers"),
            ("npg_list_ddns_records", "/api/v1/ddns-records"),
            ("npg_list_filter_subscriptions", "/api/v1/filter-subscriptions"),
        ],
    )
    def test_negative_limit_clean_error(self, recording, tool, path):
        result = _run(getattr(main_mod, tool)(limit=-2))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestListWafRules:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_waf_rules())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/waf/rules", None)]

    def test_proxy_host_id_forwarded(self, recording):
        _run(main_mod.npg_list_waf_rules(proxy_host_id="123e4567-e89b-12d3-a456-426614174000"))
        assert recording.calls == [
            (
                "GET",
                "/api/v1/waf/rules",
                {"proxy_host_id": "123e4567-e89b-12d3-a456-426614174000"},
            )
        ]

    def test_blank_proxy_host_id_not_sent(self, recording):
        _run(main_mod.npg_list_waf_rules(proxy_host_id=""))
        assert recording.calls == [("GET", "/api/v1/waf/rules", None)]

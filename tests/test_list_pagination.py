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


# ── Phase-3 batch: time-window/filter params on read/diagnostic tools ────
# All params None-defaulted: zero-arg calls stay byte-identical (no params).
# Datetime strings are forwarded verbatim; ints validated with _validate_query_int.


class TestGetLogStats:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_log_stats())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/logs/stats", None)]

    def test_time_window_forwarded_verbatim(self, recording):
        _run(
            main_mod.npg_get_log_stats(
                start_time="2026-09-16T00:00:00Z", end_time="2026-09-23T00:00:00Z"
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs/stats",
                {
                    "start_time": "2026-09-16T00:00:00Z",
                    "end_time": "2026-09-23T00:00:00Z",
                },
            )
        ]

    def test_all_filters_sent(self, recording):
        _run(
            main_mod.npg_get_log_stats(
                log_type="access",
                host="sub.example.com",
                client_ip="1.2.3.4",
                proxy_host_id="123e4567-e89b-12d3-a456-426614174000",
                block_reason="waf",
                search="admin",
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/logs/stats",
                {
                    "log_type": "access",
                    "host": "sub.example.com",
                    "client_ip": "1.2.3.4",
                    "proxy_host_id": "123e4567-e89b-12d3-a456-426614174000",
                    "block_reason": "waf",
                    "search": "admin",
                },
            )
        ]

    def test_blank_strings_not_sent(self, recording):
        _run(main_mod.npg_get_log_stats(host="  ", search=""))
        assert recording.calls == [("GET", "/api/v1/logs/stats", None)]


class TestGetExpiringCertificates:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_expiring_certificates())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/certificates/expiring", None)]

    def test_days_forwarded(self, recording):
        _run(main_mod.npg_get_expiring_certificates(days=365))
        assert recording.calls == [
            ("GET", "/api/v1/certificates/expiring", {"days": 365})
        ]

    def test_negative_days_clean_error(self, recording):
        result = _run(main_mod.npg_get_expiring_certificates(days=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestGetDashboardStats:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_dashboard_stats())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/dashboard/stats/hourly", None)]

    def test_window_and_host_forwarded(self, recording):
        _run(
            main_mod.npg_get_dashboard_stats(
                start="2026-09-16T00:00:00Z",
                end="2026-09-23T00:00:00Z",
                proxy_host_id="123e4567-e89b-12d3-a456-426614174000",
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/dashboard/stats/hourly",
                {
                    "start": "2026-09-16T00:00:00Z",
                    "end": "2026-09-23T00:00:00Z",
                    "proxy_host_id": "123e4567-e89b-12d3-a456-426614174000",
                },
            )
        ]

    def test_blank_strings_not_sent(self, recording):
        _run(main_mod.npg_get_dashboard_stats(start=" ", proxy_host_id=""))
        assert recording.calls == [("GET", "/api/v1/dashboard/stats/hourly", None)]


class TestGetDashboardHealthHistory:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_dashboard_health_history())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/dashboard/health/history", None)]

    def test_hours_and_limit_forwarded(self, recording):
        _run(main_mod.npg_get_dashboard_health_history(hours=24, limit=50))
        assert recording.calls == [
            ("GET", "/api/v1/dashboard/health/history", {"hours": 24, "limit": 50})
        ]

    def test_negative_hours_clean_error(self, recording):
        result = _run(main_mod.npg_get_dashboard_health_history(hours=-5))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestGetDashboardGeoipStats:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_dashboard_geoip_stats())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/dashboard/geoip-stats", None)]

    def test_hours_forwarded(self, recording):
        _run(main_mod.npg_get_dashboard_geoip_stats(hours=168))
        assert recording.calls == [
            ("GET", "/api/v1/dashboard/geoip-stats", {"hours": 168})
        ]

    def test_negative_hours_clean_error(self, recording):
        result = _run(main_mod.npg_get_dashboard_geoip_stats(hours=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestGetBanHistory:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_ban_history())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/banned-ips/history", None)]

    def test_filters_and_paging_sent(self, recording):
        _run(
            main_mod.npg_get_ban_history(
                ip_address="1.2.3.4",
                event_type="ban",
                source="fail2ban",
                proxy_host_id="123e4567-e89b-12d3-a456-426614174000",
                start_date="2026-09-16",
                end_date="2026-09-23",
                page=2,
                limit=10,
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/banned-ips/history",
                {
                    "ip_address": "1.2.3.4",
                    "event_type": "ban",
                    "source": "fail2ban",
                    "proxy_host_id": "123e4567-e89b-12d3-a456-426614174000",
                    "start_date": "2026-09-16",
                    "end_date": "2026-09-23",
                    "page": 2,
                    "per_page": 10,
                },
            )
        ]

    def test_limit_maps_to_per_page(self, recording):
        _run(main_mod.npg_get_ban_history(limit=5))
        assert recording.calls == [
            ("GET", "/api/v1/banned-ips/history", {"per_page": 5})
        ]

    def test_negative_page_clean_error(self, recording):
        result = _run(main_mod.npg_get_ban_history(page=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []

    def test_blank_strings_not_sent(self, recording):
        _run(main_mod.npg_get_ban_history(ip_address=" ", source=""))
        assert recording.calls == [("GET", "/api/v1/banned-ips/history", None)]


class TestGetBanHistoryForIp:
    def test_required_ip_only(self, recording):
        _run(main_mod.npg_get_ban_history_for_ip(ip="1.2.3.4"))
        assert recording.calls == [
            ("GET", "/api/v1/banned-ips/history/ip/1.2.3.4", None)
        ]

    def test_paging_sent(self, recording):
        _run(main_mod.npg_get_ban_history_for_ip(ip="1.2.3.4", page=2, limit=10))
        assert recording.calls == [
            (
                "GET",
                "/api/v1/banned-ips/history/ip/1.2.3.4",
                {"page": 2, "per_page": 10},
            )
        ]

    def test_negative_limit_clean_error(self, recording):
        result = _run(main_mod.npg_get_ban_history_for_ip(ip="1.2.3.4", limit=-3))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestListAuditLogsPhase3:
    def test_new_filters_sent(self, recording):
        _run(
            main_mod.npg_list_audit_logs(
                search="login",
                user_id="123e4567-e89b-12d3-a456-426614174000",
                start_time="2026-09-16T00:00:00Z",
                end_time="2026-09-23T00:00:00Z",
                offset=10,
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/audit-logs",
                {
                    "offset": 10,
                    "search": "login",
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "start_time": "2026-09-16T00:00:00Z",
                    "end_time": "2026-09-23T00:00:00Z",
                },
            )
        ]

    def test_negative_offset_clean_error(self, recording):
        result = _run(main_mod.npg_list_audit_logs(offset=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestListSystemLogsPhase3:
    def test_new_filters_sent(self, recording):
        _run(
            main_mod.npg_list_system_logs(
                container="npg-proxy",
                component="api",
                search="reload",
                start_time="2026-09-16T00:00:00Z",
                end_time="2026-09-23T00:00:00Z",
                offset=5,
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/system-logs",
                {
                    "offset": 5,
                    "container": "npg-proxy",
                    "component": "api",
                    "search": "reload",
                    "start_time": "2026-09-16T00:00:00Z",
                    "end_time": "2026-09-23T00:00:00Z",
                },
            )
        ]

    def test_negative_offset_clean_error(self, recording):
        result = _run(main_mod.npg_list_system_logs(offset=-2))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestWafHistory:
    def test_global_history_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_waf_global_history())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/waf/global/history", None)]

    def test_global_history_limit_forwarded(self, recording):
        _run(main_mod.npg_get_waf_global_history(limit=25))
        assert recording.calls == [("GET", "/api/v1/waf/global/history", {"limit": 25})]

    def test_global_history_negative_limit_clean_error(self, recording):
        result = _run(main_mod.npg_get_waf_global_history(limit=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []

    def test_host_history_limit_forwarded(self, recording):
        _run(
            main_mod.npg_get_waf_host_history(
                host_id="123e4567-e89b-12d3-a456-426614174000", limit=10
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/waf/hosts/123e4567-e89b-12d3-a456-426614174000/history",
                {"limit": 10},
            )
        ]

    def test_host_history_zero_arg_sends_no_params(self, recording):
        _run(main_mod.npg_get_waf_host_history(host_id="123e4567-e89b-12d3-a456-426614174000"))
        assert recording.calls == [
            (
                "GET",
                "/api/v1/waf/hosts/123e4567-e89b-12d3-a456-426614174000/history",
                None,
            )
        ]


class TestListDnsProviders:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_dns_providers())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/dns-providers", None)]

    def test_page_forwarded(self, recording):
        _run(main_mod.npg_list_dns_providers(page=3))
        assert recording.calls == [("GET", "/api/v1/dns-providers", {"page": 3})]

    def test_negative_page_clean_error(self, recording):
        result = _run(main_mod.npg_list_dns_providers(page=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


class TestGetCertificateHistory:
    def test_zero_arg_sends_no_params(self, recording):
        result = _run(main_mod.npg_get_certificate_history())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/certificates/history", None)]

    def test_page_forwarded(self, recording):
        _run(main_mod.npg_get_certificate_history(page=2))
        assert recording.calls == [("GET", "/api/v1/certificates/history", {"page": 2})]

    def test_negative_page_clean_error(self, recording):
        result = _run(main_mod.npg_get_certificate_history(page=-2))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert recording.calls == []


# ── Phase-3 parity: MCP-side limit/offset paging on the 10 remaining ─────
# list tools whose upstream endpoints IGNORE pagination query params
# (verified GET-only against the live API: responses are byte-identical
# with and without ?limit=&offset=). Paging is applied MCP-side after the
# GET; zero-arg calls must remain byte-identical to the pre-change shape.


class TestMcpSliceResponseHelper:
    def test_no_args_is_identity(self):
        data = {"data": [1, 2, 3]}
        out, meta = main_mod._mcp_slice_response(data, None, None)
        assert out is data
        assert meta is None

    def test_bare_list_window(self):
        out, meta = main_mod._mcp_slice_response([1, 2, 3, 4, 5], 2, 1)
        assert out == [2, 3]
        assert meta["total"] == 5 and meta["returned"] == 2 and meta["offset"] == 1
        assert "mcp-side" in meta["applied"]

    def test_dict_key_window(self):
        data = {"data": ["a", "b", "c"], "total": 3}
        out, meta = main_mod._mcp_slice_response(data, 2, None)
        assert out["data"] == ["a", "b"]
        assert out["total"] == 3  # non-sliced keys preserved
        assert meta["total"] == 3 and meta["returned"] == 2

    def test_offset_only_takes_tail(self):
        out, meta = main_mod._mcp_slice_response([1, 2, 3], None, 2)
        assert out == [3]
        assert meta["total"] == 3 and meta["returned"] == 1

    def test_offset_beyond_end_empty_window(self):
        out, meta = main_mod._mcp_slice_response([1, 2], 5, 10)
        assert out == []
        assert meta["total"] == 2 and meta["returned"] == 0

    def test_category_grouped_payload_slices_every_categorys_rules(self):
        data = {
            "categories": [
                {"id": "x", "name": "X", "rules": [{"id": 1}, {"id": 2}, {"id": 3}]},
                {"id": "y", "name": "Y", "rules": [{"id": 4}, {"id": 5}]},
                {"id": "z", "name": "Z"},  # no rules key — passed through
            ],
            "total_rules": 5,
        }
        out, meta = main_mod._mcp_slice_response(data, 2, 0, unit="rules", key="rules")
        assert [r["id"] for r in out["categories"][0]["rules"]] == [1, 2]
        assert [r["id"] for r in out["categories"][1]["rules"]] == [4, 5]
        assert out["categories"][2] == {"id": "z", "name": "Z"}
        assert out["total_rules"] == 5
        assert meta["total"] == 5 and meta["returned"] == 4

    def test_input_not_mutated(self):
        data = {"data": [1, 2, 3]}
        main_mod._mcp_slice_response(data, 1, None)
        assert data["data"] == [1, 2, 3]

    def test_negative_values_rejected(self):
        with pytest.raises(ValueError):
            main_mod._mcp_slice_response([1], -1, None)
        with pytest.raises(ValueError):
            main_mod._mcp_slice_response([1], None, -2)

    def test_unexpected_shape_passes_through_with_none_applied(self):
        out, meta = main_mod._mcp_slice_response({"foo": "bar"}, 2, None)
        assert out == {"foo": "bar"}
        assert "none" in meta["applied"]


class _ListFakeClient(_RecordingClient):
    """Fake client returning canned data for a fixed path."""

    def __init__(self, path, data):
        super().__init__()
        self._path = path
        self._data = data

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        assert path == self._path
        return self._data


def _fake(monkeypatch, path, data):
    client = _ListFakeClient(path, data)
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


class TestMcpSidePagedListTools:
    """Each of the 10 tools: zero-arg byte-identical + sliced w/ paging meta."""

    BARE_LIST = [{"id": i} for i in range(5)]

    def _assert_tool(self, monkeypatch, path, tool, args, key="data", unit_check=None):
        client = _fake(monkeypatch, path, list(self.BARE_LIST))

        # zero-arg: byte-identical legacy shape, no paging key
        result = _run(tool())
        assert result == {"success": True, "data": list(self.BARE_LIST)}
        assert "paging" not in result

        # limit=2, offset=1 → items[1:3] + paging metadata
        result = _run(tool(*args))
        assert result["success"] is True
        assert result["data"] == self.BARE_LIST[1:3]
        assert result["paging"]["total"] == 5
        assert result["paging"]["returned"] == 2
        assert result["paging"]["offset"] == 1
        assert "mcp-side" in result["paging"]["applied"]
        # both GETs went out with NO query params (upstream ignores them);
        # slicing happens purely MCP-side after the response
        assert client.calls == [("GET", path, None), ("GET", path, None)]

    def test_users(self, monkeypatch):
        self._assert_tool(monkeypatch, "/api/v1/users", main_mod.npg_list_users, (2, 1))

    def test_roles(self, monkeypatch):
        self._assert_tool(monkeypatch, "/api/v1/roles", main_mod.npg_list_roles, (2, 1))

    def test_sso_providers(self, monkeypatch):
        self._assert_tool(
            monkeypatch,
            "/api/v1/sso-providers",
            main_mod.npg_list_sso_providers,
            (2, 1),
        )

    def test_api_tokens(self, monkeypatch):
        self._assert_tool(
            monkeypatch, "/api/v1/api-tokens", main_mod.npg_list_api_tokens, (2, 1)
        )

    def test_cloud_providers(self, monkeypatch):
        self._assert_tool(
            monkeypatch,
            "/api/v1/cloud-providers",
            main_mod.npg_list_cloud_providers,
            (2, 1),
        )

    def test_notification_channels(self, monkeypatch):
        self._assert_tool(
            monkeypatch,
            "/api/v1/notification-channels",
            main_mod.npg_list_notification_channels,
            (2, 1),
        )

    def test_uri_blocks(self, monkeypatch):
        self._assert_tool(
            monkeypatch, "/api/v1/uri-blocks", main_mod.npg_list_uri_blocks, (2, 1)
        )

    def test_proxy_host_groups_slices_tags_only(self, monkeypatch):
        data = {"tags": [{"name": f"t{i}", "count": 1} for i in range(5)],
                "domains": ["a.com", "b.com"], "status": {"enabled": 1, "disabled": 1}}
        client = _fake(monkeypatch, "/api/v1/proxy-hosts/groups", data)
        result = _run(main_mod.npg_list_proxy_host_groups(limit=2, offset=1))
        assert result["data"]["tags"] == data["tags"][1:3]
        assert result["data"]["domains"] == ["a.com", "b.com"]  # untouched
        assert result["paging"]["total"] == 5
        # zero-arg unchanged
        result = _run(main_mod.npg_list_proxy_host_groups())
        assert result == {"success": True, "data": data}
        assert client.calls == [
            ("GET", "/api/v1/proxy-hosts/groups", None),
            ("GET", "/api/v1/proxy-hosts/groups", None),
        ]

    def test_exploit_rules_slices_per_category(self, monkeypatch):
        data = {"categories": [{"id": "c", "rules": [{"id": i} for i in range(4)]}],
                "total_rules": 4}
        client = _fake(monkeypatch, "/api/v1/exploit-rules", data)
        result = _run(main_mod.npg_list_exploit_rules(limit=2, offset=1))
        assert result["data"]["categories"][0]["rules"] == [{"id": 1}, {"id": 2}]
        assert result["data"]["total_rules"] == 4
        assert client.calls == [("GET", "/api/v1/exploit-rules", None)]

    def test_waf_rules_paging_coexists_with_proxy_host_filter(self, monkeypatch):
        data = {"categories": [{"id": "c", "rules": [{"id": i} for i in range(6)]}],
                "total_rules": 6}
        client = _fake(monkeypatch, "/api/v1/waf/rules", data)
        result = _run(main_mod.npg_list_waf_rules(
            proxy_host_id="123e4567-e89b-12d3-a456-426614174000", limit=3, offset=2))
        assert result["data"]["categories"][0]["rules"] == [
            {"id": 2}, {"id": 3}, {"id": 4},
        ]
        # upstream filter still sent; no pagination params in the query string
        assert client.calls == [("GET", "/api/v1/waf/rules", {
            "proxy_host_id": "123e4567-e89b-12d3-a456-426614174000",
        })]

    def test_negative_limit_clean_error_no_http_call(self, monkeypatch):
        users_client = _fake(monkeypatch, "/api/v1/users", [])
        result = _run(main_mod.npg_list_users(limit=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        # waf_rules: same validation, different fixture path
        waf_client = _fake(monkeypatch, "/api/v1/waf/rules", {"categories": []})
        result = _run(main_mod.npg_list_waf_rules(limit=-1))
        assert result["success"] is False
        assert "non-negative integer" in result["error"]
        assert users_client.calls == [] and waf_client.calls == []

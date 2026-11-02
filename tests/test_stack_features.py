"""Unit tests for npg_get_stack_features (report-only stack probe).

No network: ``npg_mcp.main._get_client`` is monkeypatched with a fake that
serves the ten family endpoints, so the tool's real code path runs end to end.

The contract under test:
* every family is probed with a GET only (the tool is read-only / report-only),
* a 403 permission-scope failure on one family becomes ``readable: false``
  DATA — the call still succeeds and the other families keep their values,
* an absent endpoint (404) and a transport failure behave the same way,
* counts tolerate list / enveloped / paginated / empty-body shapes,
* nothing is hidden or gated: the result never filters the tool surface.
"""

from __future__ import annotations

import asyncio

import npg_mcp.main as main_mod
from npg_mcp.client import NPGError

ENVELOPE = {
    "/api/v1/settings/cloudflare-tunnel/status": {
        "state": "connected",
        "connections": 2,
    },
    "/api/v1/settings/global-fail2ban": {
        "enabled": True,
        "action": "block",
        "max_retries": 5,
        "find_time": 600,
        "ban_time": 3600,
    },
    "/api/v1/settings/global-waf": {
        "enabled": True,
        "mode": "blocking",
        "paranoia_level": 2,
        "anomaly_threshold": 10,
    },
    "/api/v1/challenge-config": {
        "enabled": False,
        "challenge_type": "turnstile",
        "apply_to": "both",
        "has_secret_key": True,
    },
    "/api/v1/system-settings/geoip/status": {
        "enabled": False,
        "status": "disabled",
        "country_db": False,
        "asn_db": False,
        "database_version": "",
    },
    # plain list
    "/api/v1/sso-providers": {"data": [{"slug": "okta"}, {"slug": "google"}]},
    # paginated envelope with total
    "/api/v1/dns-providers": {
        "data": [{"name": "cf"}],
        "total": 1,
        "page": 1,
        "per_page": 20,
        "total_pages": 1,
    },
    # empty body (204) — the API answered with nothing to enumerate
    "/api/v1/cloud-providers": None,
    "/api/v1/ddns-records": {
        "data": [{"hostname": "a.example.com"}],
        "total": 1,
        "page": 1,
        "per_page": 20,
        "total_pages": 1,
    },
    # bare list, no envelope
    "/api/v1/notification-channels": [{"name": "hook"}],
}


class _FakeClient:
    """Fake NPGClient: serves ``ENVELOPE`` unless a path is in ``errors``."""

    def __init__(
        self,
        errors: dict[str, Exception] | None = None,
        payloads: dict[str, object] | None = None,
    ):
        self.errors = errors or {}
        self.payloads = payloads or {}
        self.calls: list[tuple[str, str]] = []

    def get(self, path, params=None):
        self.calls.append(("GET", path))
        if path in self.errors:
            raise self.errors[path]
        if path in self.payloads:
            return self.payloads[path]
        return ENVELOPE[path]


def _run_tool(monkeypatch, client):
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return asyncio.run(main_mod.npg_get_stack_features())


def test_all_families_readable(monkeypatch):
    client = _FakeClient()
    result = _run_tool(monkeypatch, client)

    assert result["success"] is True
    data = result["data"]
    assert data["report_only"] is True
    assert data["families_probed"] == 10
    assert data["families_readable"] == 10
    assert data["unreadable_families"] == []

    features = data["features"]
    assert features["cloudflare_tunnel"]["state"] == "connected"
    assert features["global_fail2ban"]["enabled"] is True
    assert features["global_fail2ban"]["ban_time"] == 3600
    assert features["global_waf"]["paranoia_level"] == 2
    assert features["challenge"]["challenge_type"] == "turnstile"
    assert features["geoip"]["status"] == "disabled"
    for entry in features.values():
        assert entry["readable"] is True

    counts = data["counts"]
    assert counts["sso_providers"]["count"] == 2
    assert counts["dns_providers"]["count"] == 1
    assert counts["cloud_providers"]["count"] == 0  # empty body
    assert counts["ddns_records"]["count"] == 1
    assert counts["notification_channels"]["count"] == 1


def test_only_gets_are_issued(monkeypatch):
    client = _FakeClient()
    _run_tool(monkeypatch, client)
    assert len(client.calls) == 10
    assert {method for method, _ in client.calls} == {"GET"}


def test_403_is_report_data_not_a_call_error(monkeypatch):
    client = _FakeClient(
        {
            "/api/v1/sso-providers": NPGError(
                "NPG API returned HTTP 403", "missing sso:read scope"
            )
        }
    )
    result = _run_tool(monkeypatch, client)

    # The call succeeds: one unreadable family says nothing about the others.
    assert result["success"] is True
    data = result["data"]
    assert data["unreadable_families"] == ["sso_providers"]
    assert data["families_readable"] == 9
    sso = data["counts"]["sso_providers"]
    assert sso["readable"] is False
    assert sso["http_status"] == 403
    assert "missing sso:read scope" in sso["error"]
    assert "count" not in sso
    # untouched family keeps its value
    assert data["counts"]["dns_providers"]["count"] == 1


def test_absent_endpoint_and_transport_failures(monkeypatch):
    client = _FakeClient(
        {
            "/api/v1/settings/global-waf": NPGError(
                "NPG API returned HTTP 404"
            ),
            "/api/v1/notification-channels": RuntimeError("connection reset"),
        }
    )
    data = _run_tool(monkeypatch, client)["data"]

    assert data["unreadable_families"] == [
        "global_waf",
        "notification_channels",
    ]
    assert data["features"]["global_waf"]["http_status"] == 404
    # non-HTTP failure: status is None, error text preserved
    assert data["counts"]["notification_channels"]["http_status"] is None
    assert data["counts"]["notification_channels"]["error"].endswith(
        "connection reset"
    )


def test_unexpected_shape_yields_null_count_not_error(monkeypatch):
    client = _FakeClient(
        payloads={"/api/v1/ddns-records": {"unexpected": "shape"}}
    )
    data = _run_tool(monkeypatch, client)["data"]

    assert data["counts"]["ddns_records"]["readable"] is True
    assert data["counts"]["ddns_records"]["count"] is None

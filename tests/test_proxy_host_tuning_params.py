"""Unit tests for the proxy-host tuning params added for MCP/API parity.

Covers, without any network access (recording fake client):
* npg_test_proxy_host — ``url`` is sent as a QUERY parameter (never a body
  field) and a bare path is rejected client-side.
* npg_update_proxy_host_security_headers — ``permissions_policy`` is exposed and
  the tool GET-merges before PUT, because the endpoint always writes
  content_security_policy / permissions_policy / custom_headers (omitting them
  clears the stored value).
* npg_update_proxy_host_upstream — health_check_timeout /
  health_check_expected_status / keepalive / name are exposed and the tool
  GET-merges before PUT, because the endpoint is a FULL-REPLACE upsert
  (omitting ``servers`` empties the pool).
* npg_add_proxy_host_uri_block_rule — ``enabled`` is forwarded only when set.

Contract facts verified against the live test API (NPG 2.72.0 swagger):
``/proxy-hosts/{id}/test`` takes ``url`` in=query; ``CreateUpstream`` is a
full-replace upsert; ``CreateSecurityHeaders`` always writes the CSP /
permissions-policy / custom-headers strings; ``AddURIBlockRule`` has an
``enabled`` boolean defaulting to true.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod


class _RecordingClient:
    def __init__(self, get_payloads=None):
        self.calls = []
        self.get_payloads = get_payloads or {}

    def get(self, path, params=None):
        self.calls.append(("GET", path, None, params))
        return self.get_payloads.get(path)

    def post(self, path, body=None, params=None):
        self.calls.append(("POST", path, body, params))
        return {"success": True}

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        return {"success": True}

    def delete(self, path, body=None, params=None):
        self.calls.append(("DELETE", path, body, params))
        return None


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def make_client(monkeypatch):
    def _make(get_payloads=None):
        client = _RecordingClient(get_payloads)
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        return client

    return _make


def _last(recording):
    return recording.calls[-1]


class TestTestProxyHostUrl:
    def test_no_url_sends_no_query(self, make_client):
        client = make_client()
        result = _run(main_mod.npg_test_proxy_host(host_id="abc"))
        assert result["success"] is True
        method, path, body, params = _last(client)
        assert method == "POST"
        assert path == "/api/v1/proxy-hosts/abc/test"
        assert body is None
        assert params is None

    def test_url_is_sent_as_query_not_body(self, make_client):
        client = make_client()
        _run(
            main_mod.npg_test_proxy_host(
                host_id="abc", url="https://example.com/api/health"
            )
        )
        method, path, body, params = _last(client)
        assert method == "POST"
        assert body is None
        assert params == {"url": "https://example.com/api/health"}

    def test_bare_path_is_rejected_before_any_call(self, make_client):
        client = make_client()
        result = _run(main_mod.npg_test_proxy_host(host_id="abc", url="/api/health"))
        assert result["success"] is False
        assert "absolute" in result["error"]
        assert client.calls == []


SEC_HEADERS_PATH = "/api/v1/proxy-hosts/abc/security-headers"


class TestSecurityHeadersPermissionsPolicy:
    def test_permissions_policy_sent_alongside_stored_csp(self, make_client):
        client = make_client(
            {
                SEC_HEADERS_PATH: {
                    "id": "",
                    "proxy_host_id": "abc",
                    "enabled": True,
                    "hsts_enabled": True,
                    "hsts_max_age": 31536000,
                    "content_security_policy": "default-src 'self'",
                    "permissions_policy": "geolocation=()",
                    "custom_headers": None,
                    "created_at": "0001-01-01T00:00:00Z",
                }
            }
        )
        result = _run(
            main_mod.npg_update_proxy_host_security_headers(
                host_id="abc", permissions_policy="camera=()"
            )
        )
        assert result["success"] is True
        assert [c[0] for c in client.calls] == ["GET", "PUT"]
        body = _last(client)[2]
        assert body["permissions_policy"] == "camera=()"
        # Stored CSP must survive — the endpoint clears it when omitted.
        assert body["content_security_policy"] == "default-src 'self'"
        # Read-only bookkeeping is not echoed back into the PUT body.
        assert "created_at" not in body
        assert "proxy_host_id" not in body

    def test_unrelated_update_preserves_stored_csp_and_policy(self, make_client):
        client = make_client(
            {
                SEC_HEADERS_PATH: {
                    "enabled": True,
                    "content_security_policy": "default-src 'none'",
                    "permissions_policy": "browsing-topics=()",
                    "custom_headers": {"X-Test": "1"},
                }
            }
        )
        _run(
            main_mod.npg_update_proxy_host_security_headers(
                host_id="abc", hsts_preload=True
            )
        )
        body = _last(client)[2]
        assert body["hsts_preload"] is True
        assert body["content_security_policy"] == "default-src 'none'"
        assert body["permissions_policy"] == "browsing-topics=()"
        assert body["custom_headers"] == {"X-Test": "1"}


UPSTREAM_PATH = "/api/v1/proxy-hosts/abc/upstream"

STORED_UPSTREAM = {
    "id": "u1",
    "proxy_host_id": "abc",
    "name": "upstream_abc",
    "scheme": "http",
    "servers": [
        {
            "address": "10.0.0.5",
            "port": 8080,
            "weight": 2,
            "max_fails": 3,
            "fail_timeout": 30,
            "is_backup": False,
            "is_down": False,
            "is_healthy": True,
            "created_at": "0001-01-01T00:00:00Z",
            "updated_at": "0001-01-01T00:00:00Z",
        }
    ],
    "load_balance": "least_conn",
    "health_check_enabled": True,
    "health_check_interval": 10,
    "health_check_timeout": 5,
    "health_check_path": "/healthz",
    "health_check_expected_status": 204,
    "keepalive": 32,
    "is_healthy": True,
}


class TestUpstreamHealthCheckAndKeepalive:
    def test_new_scalars_sent_and_servers_preserved(self, make_client):
        client = make_client({UPSTREAM_PATH: dict(STORED_UPSTREAM)})
        result = _run(
            main_mod.npg_update_proxy_host_upstream(
                host_id="abc",
                keepalive=64,
                health_check_timeout=3,
                health_check_expected_status=200,
            )
        )
        assert result["success"] is True
        assert [c[0] for c in client.calls] == ["GET", "PUT"]
        body = _last(client)[2]
        assert body["keepalive"] == 64
        assert body["health_check_timeout"] == 3
        assert body["health_check_expected_status"] == 200
        # Full-replace endpoint: servers must be re-sent, stripped of bookkeeping.
        assert body["servers"] == [
            {
                "address": "10.0.0.5",
                "port": 8080,
                "weight": 2,
                "max_fails": 3,
                "fail_timeout": 30,
                "is_backup": False,
                "is_down": False,
            }
        ]
        assert body["load_balance"] == "least_conn"
        assert body["health_check_enabled"] is True
        assert body["health_check_interval"] == 10
        assert body["health_check_path"] == "/healthz"

    def test_servers_can_still_be_replaced(self, make_client):
        client = make_client({UPSTREAM_PATH: dict(STORED_UPSTREAM)})
        _run(
            main_mod.npg_update_proxy_host_upstream(
                host_id="abc",
                servers=[{"address": "10.0.0.9", "port": 9000}],
            )
        )
        body = _last(client)[2]
        assert body["servers"] == [{"address": "10.0.0.9", "port": 9000}]
        # Scalars still preserved by the merge.
        assert body["keepalive"] == 32
        assert body["scheme"] == "http"

    def test_upstream_name_forwarded_and_validated(self, make_client):
        client = make_client({UPSTREAM_PATH: dict(STORED_UPSTREAM)})
        _run(main_mod.npg_update_proxy_host_upstream(host_id="abc", name="custom_pool"))
        assert _last(client)[2]["name"] == "custom_pool"

        bad = make_client({UPSTREAM_PATH: dict(STORED_UPSTREAM)})
        result = _run(
            main_mod.npg_update_proxy_host_upstream(host_id="abc", name="bad name")
        )
        assert result["success"] is False
        assert "^[A-Za-z0-9_]+$" in result["error"]
        assert bad.calls == []

    def test_no_stored_upstream_still_sends_only_provided_fields(self, make_client):
        client = make_client({})  # GET -> None (no upstream row yet)
        _run(main_mod.npg_update_proxy_host_upstream(host_id="abc", keepalive=16))
        method, path, body, params = _last(client)
        assert method == "PUT"
        assert body == {"keepalive": 16}


class TestUriBlockRuleEnabled:
    def test_enabled_false_is_forwarded(self, make_client):
        client = make_client()
        _run(
            main_mod.npg_add_proxy_host_uri_block_rule(
                host_id="abc", pattern="^/probe", match_type="regex", enabled=False
            )
        )
        body = _last(client)[2]
        assert body == {"pattern": "^/probe", "match_type": "regex", "enabled": False}

    def test_enabled_default_omitted(self, make_client):
        client = make_client()
        _run(main_mod.npg_add_proxy_host_uri_block_rule(host_id="abc", pattern="/old"))
        body = _last(client)[2]
        assert body == {"pattern": "/old", "match_type": "prefix"}

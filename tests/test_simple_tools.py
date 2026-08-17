"""Unit tests for npg_create_proxy_host_simple / npg_update_proxy_host_simple.

Verifies, without any network access:
* the exact request body each simple tool builds (recording fake client),
* the API endpoint + field-name mapping (ssl_force_https / certificate_id),
* required-parameter validation errors surface as {"success": False, ...}.

Monkeypatches npg_mcp.main._get_client with a recording fake so the tools'
real code paths run end to end (validation -> body build -> HTTP call shape).
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod


class _RecordingClient:
    """Fake NPGClient that records the last (method, path, body) call."""

    def __init__(self):
        self.calls = []

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        return {"id": "created"}

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        return {"id": "updated"}


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


class TestCreateProxyHostSimple:
    def test_posts_to_proxy_hosts_with_common_fields(self, recording):
        result = _run(
            main_mod.npg_create_proxy_host_simple(
                domain_names=["simple-test.four2mis.com"],
                forward_host="10.0.0.5",
                forward_port=8080,
                forward_scheme="https",
                ssl_enabled=True,
                ssl_forced=True,
                enabled=True,
                block_exploits=True,
            )
        )
        assert result == {"success": True, "data": {"id": "created"}}
        assert len(recording.calls) == 1
        method, path, body = recording.calls[0]
        assert method == "POST"
        assert path == "/api/v1/proxy-hosts"
        assert body == {
            "domain_names": ["simple-test.four2mis.com"],
            "forward_host": "10.0.0.5",
            "forward_port": 8080,
            "forward_scheme": "https",
            "ssl_enabled": True,
            "ssl_force_https": True,
            "enabled": True,
            "block_exploits": True,
        }

    def test_defaults_applied_when_omitted(self, recording):
        _run(
            main_mod.npg_create_proxy_host_simple(
                domain_names=["simple-test.four2mis.com"],
                forward_host="127.0.0.1",
                forward_port=65530,
            )
        )
        _, _, body = recording.calls[0]
        # omitted optional params are not sent; hardcoded defaults are applied
        assert "forward_scheme" not in body
        assert body["ssl_enabled"] is True
        assert body["ssl_force_https"] is True
        assert body["enabled"] is True
        assert body["block_exploits"] is True

    def test_validation_errors_flow_through(self):
        result = _run(
            main_mod.npg_create_proxy_host_simple(
                domain_names=[],
                forward_host="127.0.0.1",
                forward_port=8080,
            )
        )
        assert result["success"] is False
        assert "domain_names is required" in result["error"]


class TestUpdateProxyHostSimple:
    def test_puts_to_proxy_host_with_common_fields(self, recording):
        result = _run(
            main_mod.npg_update_proxy_host_simple(
                host_id="a7a057e9-6b31-4780-8d66-cfb920918284",
                domain_names=["simple-test.four2mis.com"],
                forward_host="10.0.0.6",
                forward_port=9090,
                forward_scheme="https",
                enabled=True,
                ssl_forced=True,
                ssl_cert_id="a7a057e9-6b31-4780-8d66-cfb920918284",
            )
        )
        assert result == {"success": True, "data": {"id": "updated"}}
        assert len(recording.calls) == 1
        method, path, body, params = recording.calls[0]
        assert method == "PUT"
        assert path == "/api/v1/proxy-hosts/a7a057e9-6b31-4780-8d66-cfb920918284"
        assert params is None
        assert body == {
            "domain_names": ["simple-test.four2mis.com"],
            "forward_host": "10.0.0.6",
            "forward_port": 9090,
            "forward_scheme": "https",
            "enabled": True,
            "ssl_force_https": True,
            "certificate_id": "a7a057e9-6b31-4780-8d66-cfb920918284",
        }

    def test_partial_update_omits_unset_fields(self, recording):
        _run(main_mod.npg_update_proxy_host_simple(host_id=42, forward_port=8081))
        _, path, body, _ = recording.calls[0]
        assert path == "/api/v1/proxy-hosts/42"
        assert body == {"forward_port": 8081}

    def test_ssl_cert_id_int_coerced_to_str(self, recording):
        _run(main_mod.npg_update_proxy_host_simple(host_id=1, ssl_cert_id=7))
        _, _, body, _ = recording.calls[0]
        assert body == {"certificate_id": "7"}

    def test_validation_errors_flow_through(self):
        result = _run(main_mod.npg_update_proxy_host_simple(host_id=""))
        assert result["success"] is False
        assert "host_id is required" in result["error"]

"""Unit tests for the proxy-host SSL/stream update params and the
cloud-provider update contract.

Covers, without any network access (recording fake client):
* npg_update_proxy_host — ssl_enabled + proxy_type/stream_* body mapping
  (previously the description advertised ssl_enabled while the signature
  could not accept it, and the 8 stream_* fields were create-only).
* npg_update_proxy_host_simple — ssl_enabled body mapping.
* npg_update_cloud_provider — ``enabled`` is a real UpdateCloudProviderRequest
  field (sent), while region/slug are create-only and rejected client-side.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        return {"data": [], "total": 0}

    def post(self, path, body=None, params=None):
        self.calls.append(("POST", path, body, params))
        return {"success": True}

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        return {"success": True}

    def delete(self, path, body=None, params=None):
        self.calls.append(("DELETE", path, body, params))
        return None


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _last_body(recording):
    method, path, body, *_ = recording.calls[-1]
    assert method == "PUT"
    return body


class TestUpdateProxyHostSsl:
    def test_ssl_enabled_is_sent(self, recording):
        _run(main_mod.npg_update_proxy_host(host_id="abc", ssl_enabled=False))
        assert _last_body(recording) == {"ssl_enabled": False}

    def test_ssl_forced_still_maps_to_ssl_force_https(self, recording):
        _run(main_mod.npg_update_proxy_host(host_id="abc", ssl_forced=True))
        assert _last_body(recording) == {"ssl_force_https": True}

    def test_ssl_fields_combine(self, recording):
        _run(
            main_mod.npg_update_proxy_host(
                host_id="abc",
                ssl_enabled=True,
                ssl_forced=True,
                ssl_http2=False,
                ssl_http3=False,
            )
        )
        assert _last_body(recording) == {
            "ssl_enabled": True,
            "ssl_force_https": True,
            "ssl_http2": False,
            "ssl_http3": False,
        }

    def test_omitted_ssl_fields_are_not_sent(self, recording):
        _run(main_mod.npg_update_proxy_host(host_id="abc", forward_port=8080))
        assert _last_body(recording) == {"forward_port": 8080}


class TestUpdateProxyHostStream:
    def test_proxy_type_and_stream_fields_are_sent(self, recording):
        _run(
            main_mod.npg_update_proxy_host(
                host_id="abc",
                proxy_type="stream",
                stream_listen_host="0.0.0.0",
                stream_listen_port=8443,
                stream_protocol="tcp",
                stream_ssl_preread=True,
                stream_accept_proxy_protocol=True,
                stream_send_proxy_protocol=False,
                stream_proxy_connect_timeout=10,
                stream_proxy_timeout=300,
            )
        )
        assert _last_body(recording) == {
            "proxy_type": "stream",
            "stream_listen_host": "0.0.0.0",
            "stream_listen_port": 8443,
            "stream_protocol": "tcp",
            "stream_ssl_preread": True,
            "stream_accept_proxy_protocol": True,
            "stream_send_proxy_protocol": False,
            "stream_proxy_connect_timeout": 10,
            "stream_proxy_timeout": 300,
        }

    def test_omitted_stream_fields_are_not_sent(self, recording):
        _run(main_mod.npg_update_proxy_host(host_id="abc", enabled=True))
        assert _last_body(recording) == {"enabled": True}


class TestUpdateProxyHostSimpleSsl:
    def test_ssl_enabled_is_sent(self, recording):
        _run(main_mod.npg_update_proxy_host_simple(host_id="abc", ssl_enabled=True))
        assert _last_body(recording) == {"ssl_enabled": True}


class TestUpdateCloudProviderContract:
    def test_enabled_is_sent(self, recording):
        _run(
            main_mod.npg_update_cloud_provider(
                slug="custom-cloud", kwargs={"enabled": False}
            )
        )
        assert _last_body(recording) == {"enabled": False}

    def test_partial_payload_passes_only_given_keys(self, recording):
        _run(
            main_mod.npg_update_cloud_provider(
                slug="custom-cloud", kwargs={"ip_ranges": ["10.0.0.0/8"]}
            )
        )
        assert _last_body(recording) == {"ip_ranges": ["10.0.0.0/8"]}

    def test_region_is_create_only(self, recording):
        result = _run(
            main_mod.npg_update_cloud_provider(
                slug="custom-cloud", kwargs={"region": "eu"}
            )
        )
        assert result["success"] is False
        assert "region" in result["error"]
        assert recording.calls == []

    def test_slug_is_create_only(self, recording):
        result = _run(
            main_mod.npg_update_cloud_provider(
                slug="custom-cloud", kwargs={"slug": "renamed"}
            )
        )
        assert result["success"] is False
        assert "slug" in result["error"]
        assert recording.calls == []

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
                waf_enabled=True,
                waf_use_global=True,
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
            "waf_enabled": True,
            "waf_use_global": True,
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
        assert body["waf_enabled"] is True
        assert body["waf_use_global"] is True

    def test_waf_can_be_disabled_explicitly(self, recording):
        _run(
            main_mod.npg_create_proxy_host_simple(
                domain_names=["simple-test.four2mis.com"],
                forward_host="127.0.0.1",
                forward_port=8080,
                waf_enabled=False,
            )
        )
        _, _, body = recording.calls[0]
        assert body["waf_enabled"] is False
        assert body["waf_use_global"] is True  # still defaults to True

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


class _GetRecordingClient:
    """Fake NPGClient that records every GET and returns a stub payload."""

    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path))
        return {"stub": path}


class TestGetProxyHostFullSections:
    def _client(self, monkeypatch):
        client = _GetRecordingClient()
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        return client

    def test_no_filter_fetches_all_11_sections(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(main_mod.npg_get_proxy_host_full("abc-123"))
        assert result["success"] is True
        assert result["sections_failed"] == []
        assert set(result["data"]) == {
            "host", "rate_limit", "bot_filter", "security_headers", "upstream",
            "geo", "challenge", "fail2ban", "cloud_blocking", "waf", "uri_block",
        }
        assert len(client.calls) == 11
        assert client.calls[0] == ("GET", "/api/v1/proxy-hosts/abc-123")
        assert ("GET", "/api/v1/waf/hosts/abc-123/config") in client.calls

    def test_sections_filter_only_fetches_selected(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(main_mod.npg_get_proxy_host_full("abc-123", sections=["geo", "fail2ban"]))
        assert result["success"] is True
        assert result["sections_failed"] == []
        assert set(result["data"]) == {"geo", "fail2ban"}
        assert len(client.calls) == 2
        assert client.calls == [
            ("GET", "/api/v1/proxy-hosts/abc-123/geo"),
            ("GET", "/api/v1/proxy-hosts/abc-123/fail2ban"),
        ]

    def test_invalid_section_lists_valid_names(self, monkeypatch):
        self._client(monkeypatch)
        result = _run(main_mod.npg_get_proxy_host_full("abc-123", sections=["bogus"]))
        assert result["success"] is False
        assert "bogus" in result["error"]
        for name in ["host", "geo", "fail2ban", "uri_block"]:
            assert name in result["error"]

    def test_duplicates_are_deduped_preserving_order(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(
            main_mod.npg_get_proxy_host_full("abc-123", sections=["waf", "geo", "waf"])
        )
        assert result["success"] is True
        assert set(result["data"]) == {"waf", "geo"}
        assert len(client.calls) == 2
        assert client.calls == [
            ("GET", "/api/v1/waf/hosts/abc-123/config"),
            ("GET", "/api/v1/proxy-hosts/abc-123/geo"),
        ]

    def test_section_failure_recorded_not_raised(self, monkeypatch):
        class _FailingGeo(_GetRecordingClient):
            def get(self, path, params=None):
                if path.endswith("/geo"):
                    raise RuntimeError("NPG API returned HTTP 404")
                return super().get(path, params=params)

        client = _FailingGeo()
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        result = _run(main_mod.npg_get_proxy_host_full("abc-123", sections=["host", "geo"]))
        assert result["success"] is True
        assert result["sections_failed"] == ["geo"]
        assert result["data"]["geo"]["success"] is False
        assert result["data"]["host"]["success"] is True

    def test_int_host_id_coerced_to_str(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(main_mod.npg_get_proxy_host_full(42, sections=["host"]))
        assert result["success"] is True
        assert client.calls == [("GET", "/api/v1/proxy-hosts/42")]

    def test_sections_fetched_concurrently(self, monkeypatch):
        """Wall time ~= slowest single section, not the sum of all sections."""
        import time

        delay = 0.1
        active = 0
        max_active = 0

        class _SlowClient(_GetRecordingClient):
            def get(self, path, params=None):
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                time.sleep(delay)
                active -= 1
                return super().get(path, params=params)

        client = _SlowClient()
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        start = time.monotonic()
        result = _run(main_mod.npg_get_proxy_host_full("abc-123"))
        elapsed = time.monotonic() - start

        assert result["success"] is True
        assert result["sections_failed"] == []
        assert len(result["data"]) == 11
        # sequential would be ~11 * delay = 1.1s; concurrent ~= max(delay)
        assert elapsed < 5 * delay, f"sections appear sequential: {elapsed:.2f}s"
        assert max_active > 1, "section GETs did not overlap"

    def test_concurrent_failure_isolation(self, monkeypatch):
        """One failing section lands in sections_failed; others still succeed."""

        class _FailingUpstream(_GetRecordingClient):
            def get(self, path, params=None):
                if path.endswith("/upstream"):
                    raise RuntimeError("NPG API returned HTTP 500")
                return super().get(path, params=params)

        client = _FailingUpstream()
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        result = _run(main_mod.npg_get_proxy_host_full("abc-123"))
        assert result["success"] is True
        assert result["sections_failed"] == ["upstream"]
        assert result["data"]["upstream"]["success"] is False
        assert "500" in result["data"]["upstream"]["error"]
        assert all(
            result["data"][s]["success"] is True
            for s in result["data"] if s != "upstream"
        )

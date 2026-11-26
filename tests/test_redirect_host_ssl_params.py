"""Unit tests for the redirect-host SSL / forwarding parity params.

Covers, without any network access (recording fake client):
* npg_create_redirect_host — a bare call still emits only the five original
  fields (backward compatibility: no new key appears unless asked for).
* npg_create_redirect_host — ``ssl_cert_id`` is sent as the API's
  ``certificate_id`` field with the RAW value (``_id_str``, never
  percent-encoded ``_id_path``); an empty string is rejected client-side
  because the API answers HTTP 400 ``Invalid identifier format`` for it.
* npg_update_redirect_host — partial semantics: only the keys the caller
  passed reach the body (``forward_path`` alone emits exactly one key).
* npg_update_redirect_host — the new booleans map to their API field names
  (``ssl_force_https`` for force-HTTPS) and are sent when False.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod

UUID = "615aabe5-c513-4db5-9196-c24b604716b2"


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        return {"data": []}

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


def _last(recording, method):
    m, path, body, *_ = recording.calls[-1]
    assert m == method
    return path, body


class TestCreateRedirectHost:
    def test_bare_create_emits_only_original_fields(self, recording):
        _run(
            main_mod.npg_create_redirect_host(
                domain_names=["r.example.com"], forward_domain_name="target.example.com"
            )
        )
        path, body = _last(recording, "POST")
        assert path == "/api/v1/redirect-hosts"
        assert body == {
            "domain_names": ["r.example.com"],
            "forward_domain_name": "target.example.com",
            "forward_scheme": "auto",
            "preserve_path": True,
            "redirect_code": 301,
        }

    def test_ssl_and_forwarding_params_map_to_api_fields(self, recording):
        _run(
            main_mod.npg_create_redirect_host(
                domain_names=["r.example.com"],
                forward_domain_name="target.example.com",
                forward_path="/landing",
                ssl_enabled=False,
                ssl_cert_id=UUID,
                ssl_force_https=False,
                enabled=True,
                block_exploits=False,
            )
        )
        _, body = _last(recording, "POST")
        assert body["forward_path"] == "/landing"
        assert body["ssl_enabled"] is False
        assert body["ssl_force_https"] is False
        assert body["enabled"] is True
        assert body["block_exploits"] is False
        # API field name, raw (unencoded) UUID, and never the MCP-side name.
        assert body["certificate_id"] == UUID
        assert "ssl_cert_id" not in body
        assert "%" not in body["certificate_id"]

    def test_integer_ssl_cert_id_is_coerced_to_raw_string(self, recording):
        _run(
            main_mod.npg_create_redirect_host(
                domain_names=["r.example.com"],
                forward_domain_name="target.example.com",
                ssl_cert_id=42,
            )
        )
        _, body = _last(recording, "POST")
        assert body["certificate_id"] == "42"

    def test_forward_path_sent_verbatim(self, recording):
        # NPG normalises the path; the tool must not synthesise a leading "/".
        _run(
            main_mod.npg_create_redirect_host(
                domain_names=["r.example.com"],
                forward_domain_name="target.example.com",
                forward_path="landing",
            )
        )
        _, body = _last(recording, "POST")
        assert body["forward_path"] == "landing"

    def test_empty_ssl_cert_id_is_rejected_client_side(self, recording):
        res = _run(
            main_mod.npg_create_redirect_host(
                domain_names=["r.example.com"],
                forward_domain_name="target.example.com",
                ssl_cert_id="",
            )
        )
        assert res["success"] is False
        assert "empty string" in res["error"]
        assert recording.calls == []


class TestUpdateRedirectHost:
    def test_forward_path_alone_emits_only_that_key(self, recording):
        _run(main_mod.npg_update_redirect_host(host_id=UUID, forward_path="/other"))
        path, body = _last(recording, "PUT")
        assert path == f"/api/v1/redirect-hosts/{UUID}"
        assert body == {"forward_path": "/other"}

    def test_partial_update_keeps_untouched_fields_out_of_body(self, recording):
        _run(
            main_mod.npg_update_redirect_host(
                host_id=UUID,
                forward_path="/other",
                ssl_force_https=True,
            )
        )
        _, body = _last(recording, "PUT")
        assert body == {"forward_path": "/other", "ssl_force_https": True}

    def test_false_booleans_are_sent_not_dropped(self, recording):
        _run(
            main_mod.npg_update_redirect_host(
                host_id=UUID, enabled=False, block_exploits=False, ssl_enabled=False
            )
        )
        _, body = _last(recording, "PUT")
        assert body == {"enabled": False, "block_exploits": False, "ssl_enabled": False}

    def test_empty_ssl_cert_id_is_rejected_client_side(self, recording):
        # Live 2.72.0: PUT {certificate_id: ""} answers HTTP 400
        # "Invalid identifier format" — an empty value cannot clear a cert.
        res = _run(main_mod.npg_update_redirect_host(host_id=UUID, ssl_cert_id=""))
        assert res["success"] is False
        assert "empty string" in res["error"]
        assert "Invalid identifier format" in res["error"]
        assert recording.calls == []  # rejected before any HTTP call

    def test_no_params_emits_empty_body(self, recording):
        _run(main_mod.npg_update_redirect_host(host_id=UUID))
        _, body = _last(recording, "PUT")
        assert body == {}

"""Unit tests for the v2.57.0 proxy-host tags/groups additions.

Covers, without any network access (recording fake client):
* npg_list_proxy_host_groups — GET /api/v1/proxy-hosts/groups, zero params
* npg_list_proxy_hosts — tag/domain/upstream/enabled query-param building
  (repeatable 'tag' list, enabled -> "true"/"false", empty filters omitted)
* npg_create_proxy_host / npg_update_proxy_host — tags body mapping:
  None omitted, [] sent (tri-state clear), non-empty list passed through
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


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


class TestListProxyHostGroups:
    def test_sends_no_params(self, recording):
        result = _run(main_mod.npg_list_proxy_host_groups())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/proxy-hosts/groups", None)]


class TestListProxyHostsFilters:
    def test_tag_list_sent_as_repeatable_param(self, recording):
        _run(main_mod.npg_list_proxy_hosts(tags=["media", "test_2"]))
        assert recording.calls == [
            ("GET", "/api/v1/proxy-hosts", {"tag": ["media", "test_2"]})
        ]

    def test_filters_combined(self, recording):
        _run(
            main_mod.npg_list_proxy_hosts(
                tags=["media"], domain="app", upstream="127.0.0.1", enabled=True
            )
        )
        assert recording.calls == [
            (
                "GET",
                "/api/v1/proxy-hosts",
                {
                    "tag": ["media"],
                    "domain": "app",
                    "upstream": "127.0.0.1",
                    "enabled": "true",
                },
            )
        ]

    def test_enabled_false_serialized(self, recording):
        _run(main_mod.npg_list_proxy_hosts(enabled=False))
        assert recording.calls == [
            ("GET", "/api/v1/proxy-hosts", {"enabled": "false"})
        ]

    def test_empty_tags_and_whitespace_omitted(self, recording):
        result = _run(
            main_mod.npg_list_proxy_hosts(tags=[], domain="  ", upstream="  ")
        )
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/proxy-hosts", None)]

    def test_zero_arg_regression(self, recording):
        result = _run(main_mod.npg_list_proxy_hosts())
        assert result["success"] is True
        assert recording.calls == [("GET", "/api/v1/proxy-hosts", None)]


class TestCreateProxyHostTags:
    def test_tags_sent_in_body(self, recording):
        _run(
            main_mod.npg_create_proxy_host(
                domain_names=["t.example.com"],
                forward_host="127.0.0.1",
                forward_port=80,
                tags=["Media", "TEST_2"],
            )
        )
        method, path, body, _ = recording.calls[0]
        assert (method, path) == ("POST", "/api/v1/proxy-hosts")
        assert body["tags"] == ["Media", "TEST_2"]

    def test_tags_omitted_when_none(self, recording):
        _run(
            main_mod.npg_create_proxy_host(
                domain_names=["t.example.com"],
                forward_host="127.0.0.1",
                forward_port=80,
            )
        )
        _, _, body, _ = recording.calls[0]
        assert "tags" not in body


class TestUpdateProxyHostTags:
    def test_tags_explicit_empty_list_sent(self, recording):
        _run(main_mod.npg_update_proxy_host(host_id="abc", tags=[]))
        method, path, body, _ = recording.calls[0]
        assert (method, path) == ("PUT", "/api/v1/proxy-hosts/abc")
        assert body == {"tags": []}

    def test_tags_omitted_when_none(self, recording):
        _run(main_mod.npg_update_proxy_host(host_id="abc"))
        _, _, body, _ = recording.calls[0]
        assert "tags" not in body
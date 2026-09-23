"""Unit tests for mutation query-param side-effect controls.

Verifies, without any network access (recording fake client), that the new
upstream query params are wired exactly and only when requested:

skip_reload (save without nginx regen/reload for that host):
* npg_update_proxy_host_bot_filter(skip_reload=True) sends
  params={"skip_reload": "true"}; omitted sends no params (regression),
* npg_update_proxy_host_uri_block(skip_reload=True) sends the param,
* npg_update_proxy_host_cloud_blocking(skip_reload=True) sends the param
  (read-modify-write still issues the GET first),
* npg_create_proxy_host_geo(skip_reload=True) POSTs with the param,
* npg_delete_proxy_host_geo(skip_reload=True) DELETEs with the param,
* skip_reload=False behaves exactly like omitted (no params).

ddns_remove_provider (PUT /proxy-hosts/{id} query param):
* npg_update_proxy_host(ddns_remove_provider=True) sends
  params={"ddns_remove_provider": "true"} alongside skip_nginx when both set,
* omitted/False sends no ddns_remove_provider param (regression),
* the param never leaks into the request BODY (_build_body whitelist).

remove_provider on DELETE /ddns-records/{id}:
* npg_delete_ddns_record(remove_provider=False) sends
  params={"remove_provider": "false"} (KEEP the provider record),
* default (None) sends no params (upstream default deletes at provider),
* remove_provider=True sends no params either (upstream default).

Monkeypatches npg_mcp.main._get_client with a recording fake so the tools'
real code paths run end to end.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod


class _RecordingClient:
    """Fake NPGClient recording every (method, path, body, params) call."""

    def __init__(self, get_response=None):
        self.calls = []
        self._get_response = get_response

    def get(self, path, params=None):
        self.calls.append(("GET", path, None, params))
        return self._get_response

    def post(self, path, body=None, params=None):
        self.calls.append(("POST", path, body, params))
        return {"created": True}

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        return {"updated": True}

    def delete(self, path, params=None):
        self.calls.append(("DELETE", path, None, params))
        return None


def _client_with_empty_lists():
    # cloud blocking read-modify-write expects a dict from GET.
    return _RecordingClient(get_response={})


@pytest.fixture
def recording(monkeypatch):
    client = _client_with_empty_lists()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _params_of(recording, method, path_fragment):
    for m, path, _body, params in recording.calls:
        if m == method and path_fragment in path:
            return params
    raise AssertionError(f"no {method} call matching {path_fragment}")


class TestBotFilterSkipReload:
    HOST = "11111111-1111-1111-1111-111111111111"

    def test_skip_reload_true_sends_param(self, recording):
        result = _run(main_mod.npg_update_proxy_host_bot_filter(
            host_id=self.HOST, enabled=True, skip_reload=True))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/bot-filter") == {"skip_reload": "true"}

    def test_omitted_sends_no_params_regression(self, recording):
        result = _run(main_mod.npg_update_proxy_host_bot_filter(
            host_id=self.HOST, enabled=True))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/bot-filter") is None

    def test_false_sends_no_params(self, recording):
        result = _run(main_mod.npg_update_proxy_host_bot_filter(
            host_id=self.HOST, enabled=True, skip_reload=False))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/bot-filter") is None


class TestUriBlockSkipReload:
    HOST = "11111111-1111-1111-1111-111111111111"

    def test_skip_reload_true_sends_param(self, recording):
        result = _run(main_mod.npg_update_proxy_host_uri_block(
            host_id=self.HOST, enabled=True, skip_reload=True))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/uri-block") == {"skip_reload": "true"}

    def test_omitted_sends_no_params_regression(self, recording):
        result = _run(main_mod.npg_update_proxy_host_uri_block(
            host_id=self.HOST, enabled=True))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/uri-block") is None


class TestCloudBlockingSkipReload:
    HOST = "11111111-1111-1111-1111-111111111111"

    def test_skip_reload_true_sends_param(self, recording):
        result = _run(main_mod.npg_update_proxy_host_cloud_blocking(
            host_id=self.HOST, blocked_providers=["aws"], skip_reload=True))
        assert result["success"] is True
        # GET first (read-modify-write), then PUT with the query param.
        assert recording.calls[0][0] == "GET"
        assert _params_of(
            recording, "PUT", "/blocked-cloud-providers") == {"skip_reload": "true"}

    def test_omitted_sends_no_params_regression(self, recording):
        result = _run(main_mod.npg_update_proxy_host_cloud_blocking(
            host_id=self.HOST, blocked_providers=["aws"]))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/blocked-cloud-providers") is None


class TestGeoSkipReload:
    HOST = "11111111-1111-1111-1111-111111111111"
    COUNTRIES = ["KR"]

    def test_create_skip_reload_true_sends_param(self, recording):
        result = _run(main_mod.npg_create_proxy_host_geo(
            host_id=self.HOST, countries=self.COUNTRIES, skip_reload=True))
        assert result["success"] is True
        assert _params_of(recording, "POST", "/geo") == {"skip_reload": "true"}

    def test_create_omitted_sends_no_params_regression(self, recording):
        result = _run(main_mod.npg_create_proxy_host_geo(
            host_id=self.HOST, countries=self.COUNTRIES))
        assert result["success"] is True
        assert _params_of(recording, "POST", "/geo") is None

    def test_delete_skip_reload_true_sends_param(self, recording):
        result = _run(main_mod.npg_delete_proxy_host_geo(
            host_id=self.HOST, skip_reload=True))
        assert result["success"] is True
        assert _params_of(recording, "DELETE", "/geo") == {"skip_reload": "true"}

    def test_delete_omitted_sends_no_params_regression(self, recording):
        result = _run(main_mod.npg_delete_proxy_host_geo(host_id=self.HOST))
        assert result["success"] is True
        assert _params_of(recording, "DELETE", "/geo") is None


class TestUpdateProxyHostDdnsRemoveProvider:
    HOST = "11111111-1111-1111-1111-111111111111"

    def test_true_sends_param(self, recording):
        result = _run(main_mod.npg_update_proxy_host(
            host_id=self.HOST, forward_port=8081, ddns_remove_provider=True))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/api/v1/proxy-hosts/" + self.HOST) == {
            "ddns_remove_provider": "true"}

    def test_true_coexists_with_skip_nginx(self, recording):
        result = _run(main_mod.npg_update_proxy_host(
            host_id=self.HOST, forward_port=8081,
            skip_nginx=True, ddns_remove_provider=True))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/api/v1/proxy-hosts/" + self.HOST) == {
            "skip_nginx": "true", "ddns_remove_provider": "true"}

    def test_omitted_sends_no_params_regression(self, recording):
        result = _run(main_mod.npg_update_proxy_host(
            host_id=self.HOST, forward_port=8081))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/api/v1/proxy-hosts/" + self.HOST) is None

    def test_false_sends_no_param(self, recording):
        result = _run(main_mod.npg_update_proxy_host(
            host_id=self.HOST, forward_port=8081, ddns_remove_provider=False))
        assert result["success"] is True
        assert _params_of(recording, "PUT", "/api/v1/proxy-hosts/" + self.HOST) is None

    def test_param_never_leaks_into_body(self, recording):
        result = _run(main_mod.npg_update_proxy_host(
            host_id=self.HOST, forward_port=8081, ddns_remove_provider=True))
        assert result["success"] is True
        for m, _path, body, _params in recording.calls:
            if m == "PUT":
                assert "ddns_remove_provider" not in body


class TestDeleteDdnsRecordRemoveProvider:
    RID = "22222222-2222-2222-2222-222222222222"

    def test_false_keeps_provider_record(self, recording):
        result = _run(main_mod.npg_delete_ddns_record(
            record_id=self.RID, remove_provider=False))
        assert result["success"] is True
        assert _params_of(
            recording, "DELETE", "/ddns-records/") == {"remove_provider": "false"}

    def test_default_deletes_at_provider_regression(self, recording):
        result = _run(main_mod.npg_delete_ddns_record(record_id=self.RID))
        assert result["success"] is True
        assert _params_of(recording, "DELETE", "/ddns-records/") is None

    def test_true_sends_nothing_upstream_default(self, recording):
        result = _run(main_mod.npg_delete_ddns_record(
            record_id=self.RID, remove_provider=True))
        assert result["success"] is True
        assert _params_of(recording, "DELETE", "/ddns-records/") is None

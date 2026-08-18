"""Unit tests for npg_bulk_apply_certificate / npg_bulk_delete_proxy_hosts.

Verifies, without any network access (recording fake client):
* each bulk tool loops the existing per-host endpoint once per host_id,
* the exact per-host request shape (PUT body {"certificate_id": ...} for the
  cert apply; DELETE for the delete),
* per-host aggregation: one failing host does not abort the batch,
* the 50-host hard cap raises ValueError (surfaced as success:false),
* empty host_ids are rejected with a clear error,
* results carry host_id + success + result|error per entry.

Monkeypatches npg_mcp.main._get_client with a recording fake so the tools'
real code paths run end to end (validation -> loop -> HTTP call shape).
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod
from npg_mcp.main import _BULK_HOST_LIMIT


class _RecordingClient:
    """Fake NPGClient that records every (method, path, body) call.

    ``put`` raises NPGError for host ids starting with "fail-" so tests can
    exercise the per-host error aggregation without a real network.
    """

    def __init__(self):
        self.calls = []

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        if "fail-" in path:
            from npg_mcp.client import NPGError

            raise NPGError("NPG API returned HTTP 404", "proxy host not found")
        return {"id": path.rsplit("/", 1)[-1], "updated": True}

    def delete(self, path, params=None):
        self.calls.append(("DELETE", path, params))
        if "fail-" in path:
            from npg_mcp.client import NPGError

            raise NPGError("NPG API returned HTTP 404", "proxy host not found")
        return None


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _many_ids(n: int) -> list[str | int]:
    return [f"host-{i:03d}" for i in range(n)]


class TestBulkApplyCertificate:
    def test_applies_cert_to_each_host_via_put(self, recording):
        result = _run(
            main_mod.npg_bulk_apply_certificate(
                cert_id="a7a057e9-6b31-4780-8d66-cfb920918284",
                host_ids=["11111111-1111-1111-1111-111111111111",
                          "22222222-2222-2222-2222-222222222222"],
            )
        )
        assert result["success"] is True
        assert len(recording.calls) == 2
        assert all(method == "PUT" for method, _, _, _ in recording.calls)
        for (method, path, body, params), expected_id in zip(
            recording.calls, ["11111111-1111-1111-1111-111111111111",
                              "22222222-2222-2222-2222-222222222222"]
        ):
            assert path == f"/api/v1/proxy-hosts/{expected_id}"
            assert body == {"certificate_id": "a7a057e9-6b31-4780-8d66-cfb920918284"}
            assert params is None
        assert result["data"] == [
            {"host_id": "11111111-1111-1111-1111-111111111111", "success": True,
             "result": {"id": "11111111-1111-1111-1111-111111111111", "updated": True}},
            {"host_id": "22222222-2222-2222-2222-222222222222", "success": True,
             "result": {"id": "22222222-2222-2222-2222-222222222222", "updated": True}},
        ]

    def test_one_bad_host_does_not_abort_batch(self, recording):
        result = _run(
            main_mod.npg_bulk_apply_certificate(
                cert_id="cert-1",
                host_ids=["ok-host", "fail-host", "ok-2"],
            )
        )
        assert result["success"] is True
        assert len(recording.calls) == 3  # every host was attempted
        assert result["data"][0]["success"] is True
        assert result["data"][1]["success"] is False
        assert "404" in result["data"][1]["error"]
        assert result["data"][2]["success"] is True

    def test_int_host_ids_coerced_to_string_paths(self, recording):
        result = _run(main_mod.npg_bulk_apply_certificate(cert_id=7, host_ids=[1, 2]))
        assert result["success"] is True
        assert recording.calls[0][1] == "/api/v1/proxy-hosts/1"
        assert recording.calls[0][2] == {"certificate_id": "7"}
        assert recording.calls[1][2] == {"certificate_id": "7"}
        assert result["data"][0]["host_id"] == "1"

    def test_cert_id_required(self):
        result = _run(main_mod.npg_bulk_apply_certificate(cert_id="", host_ids=["h1"]))
        assert result["success"] is False
        assert "cert_id is required" in result["error"]

    def test_empty_host_ids_rejected(self):
        result = _run(main_mod.npg_bulk_apply_certificate(cert_id="c1", host_ids=[]))
        assert result["success"] is False
        assert "host_ids is required" in result["error"]

    def test_cap_raises_value_error_before_any_call(self, recording):
        result = _run(
            main_mod.npg_bulk_apply_certificate(
                cert_id="c1", host_ids=_many_ids(_BULK_HOST_LIMIT + 1)
            )
        )
        assert result["success"] is False
        assert f"exceeds the limit of {_BULK_HOST_LIMIT}" in result["error"]
        assert recording.calls == []  # nothing was sent

    def test_at_cap_is_allowed(self, recording):
        result = _run(
            main_mod.npg_bulk_apply_certificate(
                cert_id="c1", host_ids=_many_ids(_BULK_HOST_LIMIT)
            )
        )
        assert result["success"] is True
        assert len(recording.calls) == _BULK_HOST_LIMIT


class TestBulkDeleteProxyHosts:
    def test_deletes_each_host_via_delete(self, recording):
        result = _run(
            main_mod.npg_bulk_delete_proxy_hosts(
                host_ids=["33333333-3333-3333-3333-333333333333",
                          "44444444-4444-4444-4444-444444444444"],
            )
        )
        assert result["success"] is True
        assert len(recording.calls) == 2
        assert all(method == "DELETE" for method, _, _ in recording.calls)
        assert recording.calls[0][1] == (
            "/api/v1/proxy-hosts/33333333-3333-3333-3333-333333333333"
        )
        assert recording.calls[1][1] == (
            "/api/v1/proxy-hosts/44444444-4444-4444-4444-444444444444"
        )
        assert result["data"] == [
            {"host_id": "33333333-3333-3333-3333-333333333333", "success": True,
             "result": {"deleted": True}},
            {"host_id": "44444444-4444-4444-4444-444444444444", "success": True,
             "result": {"deleted": True}},
        ]

    def test_one_bad_host_does_not_abort_batch(self, recording):
        result = _run(
            main_mod.npg_bulk_delete_proxy_hosts(
                host_ids=["ok-host", "fail-host", "ok-2"]
            )
        )
        assert result["success"] is True
        assert len(recording.calls) == 3
        assert result["data"][0]["success"] is True
        assert result["data"][1]["success"] is False
        assert "404" in result["data"][1]["error"]
        assert result["data"][2]["success"] is True

    def test_empty_host_ids_rejected(self):
        result = _run(main_mod.npg_bulk_delete_proxy_hosts(host_ids=[]))
        assert result["success"] is False
        assert "host_ids is required" in result["error"]

    def test_cap_raises_value_error_before_any_call(self, recording):
        result = _run(
            main_mod.npg_bulk_delete_proxy_hosts(
                host_ids=_many_ids(_BULK_HOST_LIMIT + 1)
            )
        )
        assert result["success"] is False
        assert f"exceeds the limit of {_BULK_HOST_LIMIT}" in result["error"]
        assert recording.calls == []

    def test_invalid_individual_host_id_reported_per_host(self, recording):
        # A blank/None host_id in the middle must be reported as a per-host
        # error while the valid entries still run (never aborts the batch).
        from typing import cast

        bad_ids: list[str | int] = cast(list[str | int], ["ok-host", None, "ok-2"])
        result = _run(main_mod.npg_bulk_delete_proxy_hosts(host_ids=bad_ids))
        assert result["success"] is True
        assert result["data"][0]["success"] is True
        assert result["data"][1]["success"] is False
        assert "host_id is required" in result["data"][1]["error"]
        assert result["data"][2]["success"] is True

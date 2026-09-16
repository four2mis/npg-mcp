"""Unit tests for bounded-concurrency fan-out in the bulk tools.

Covers the _gather_bounded helper plus the concurrency behavior of:
* npg_bulk_apply_certificate  (cap _BULK_WRITE_CONCURRENCY = 8)
* npg_bulk_delete_proxy_hosts (cap _BULK_WRITE_CONCURRENCY = 8)
* npg_bulk_renew_certificates (cap _BULK_RENEW_CONCURRENCY = 4, ACME-friendly)
* npg_bulk_get_proxy_host_full (two-level cap: _BULK_HOST_CONCURRENCY = 16
  host workers x _BULK_SECTION_CONCURRENCY = 8 section GETs)

All tests run against fake clients with no network access:
* a fake whose methods block in a worker thread (mirroring the real
  NPGClient, which is synchronous and wrapped by _api's asyncio.to_thread)
  for _DELAY seconds while tracking in-flight/peak concurrency via a lock,
  asserting (1) wall time ~= ceil(n/cap) * delay rather than n * delay,
  (2) peak in-flight calls never exceed the cap, and
* per-entry failure isolation under the concurrent path (one failing id
  never aborts the batch, order preserved).
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

import npg_mcp.main as main_mod
from npg_mcp.main import (
    _BULK_HOST_CONCURRENCY,
    _BULK_HOST_LIMIT,
    _BULK_RENEW_CONCURRENCY,
    _BULK_SECTION_CONCURRENCY,
    _BULK_WRITE_CONCURRENCY,
    _gather_bounded,
)

_DELAY = 0.05


class _SlowFakeClient:
    """Synchronous fake NPGClient (real client shape for _api/to_thread).

    Each call blocks _DELAY seconds in a worker thread and tracks in-flight
    / peak concurrency under a lock. Paths containing ``fail-`` raise
    NPGError like a real 404 would.
    """

    def __init__(self, fail_substring: str = "fail-"):
        self.in_flight = 0
        self.peak = 0
        self.calls = 0
        self.fail_substring = fail_substring
        self._lock = threading.Lock()

    def _gate(self):
        with self._lock:
            self.calls += 1
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        time.sleep(_DELAY)
        with self._lock:
            self.in_flight -= 1

    def _fail_if(self, path):
        if self.fail_substring in path:
            from npg_mcp.client import NPGError

            raise NPGError("NPG API returned HTTP 404", "not found")

    def put(self, path, body=None, params=None):
        self._gate()
        self._fail_if(path)
        return {"id": path.rsplit("/", 1)[-1], "updated": True}

    def delete(self, path, params=None):
        self._gate()
        self._fail_if(path)
        return None

    def post(self, path, body=None, params=None):
        self._gate()
        self._fail_if(path)
        return {"id": path.rsplit("/", 2)[-2], "renewed": True}

    def get(self, path, params=None):
        self._gate()
        self._fail_if(path)
        return {"ok": True}


@pytest.fixture
def slow(monkeypatch):
    client = _SlowFakeClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _many_ids(n: int, prefix: str = "host") -> list[str | int]:
    return [f"{prefix}-{i:03d}" for i in range(n)]


class TestGatherBounded:
    def test_preserves_input_order(self):
        async def mk(i):
            # Later inputs finish first — order must still be preserved.
            await asyncio.sleep(_DELAY * (10 - i) / 10)
            return i

        result = _run(_gather_bounded(3, (mk(i) for i in range(10))))
        assert result == list(range(10))

    def test_caps_concurrency(self):
        peak = 0
        in_flight = 0

        async def mk():
            nonlocal peak, in_flight
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(_DELAY)
            in_flight -= 1

        _run(_gather_bounded(3, (mk() for _ in range(12))))
        assert peak == 3  # never exceeds the cap, but does run concurrently

    def test_empty_input(self):
        assert _run(_gather_bounded(4, iter(()))) == []

    def test_exception_propagates(self):
        async def boom():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            _run(_gather_bounded(2, (boom() for _ in range(3))))


class TestBulkApplyCertificateConcurrency:
    def test_wall_time_bounded_not_sequential(self, slow):
        n = 3 * _BULK_WRITE_CONCURRENCY  # exactly 3 full waves
        t0 = time.monotonic()
        result = _run(
            main_mod.npg_bulk_apply_certificate(cert_id="c1", host_ids=_many_ids(n))
        )
        elapsed = time.monotonic() - t0
        assert result["success"] is True
        # Sequential would be n * _DELAY (2.4s at defaults); bounded is
        # ceil(n / cap) * _DELAY = 3 waves. Allow generous slack for CI.
        assert elapsed < n * _DELAY * 0.6
        assert elapsed >= 3 * _DELAY * 0.9

    def test_peak_concurrency_never_exceeds_cap(self, slow):
        n = 2 * _BULK_WRITE_CONCURRENCY + 3
        result = _run(
            main_mod.npg_bulk_apply_certificate(cert_id="c1", host_ids=_many_ids(n))
        )
        assert result["success"] is True
        assert slow.peak <= _BULK_WRITE_CONCURRENCY
        assert slow.peak > 1  # actually parallel, not accidentally sequential
        assert slow.calls == n

    def test_order_preserved_and_isolation(self, slow):
        ids = ["ok-a", "fail-b", "ok-c", "fail-d"]
        result = _run(main_mod.npg_bulk_apply_certificate(cert_id="c1", host_ids=ids))
        assert result["success"] is True
        assert [e["host_id"] for e in result["data"]] == ids
        assert [e["success"] for e in result["data"]] == [True, False, True, False]
        assert slow.calls == len(ids)  # every entry attempted


class TestBulkDeleteProxyHostsConcurrency:
    def test_wall_time_bounded_not_sequential(self, slow):
        n = 3 * _BULK_WRITE_CONCURRENCY
        t0 = time.monotonic()
        result = _run(main_mod.npg_bulk_delete_proxy_hosts(host_ids=_many_ids(n)))
        elapsed = time.monotonic() - t0
        assert result["success"] is True
        assert elapsed < n * _DELAY * 0.6
        assert elapsed >= 3 * _DELAY * 0.9

    def test_peak_concurrency_never_exceeds_cap(self, slow):
        n = 2 * _BULK_WRITE_CONCURRENCY + 5
        result = _run(main_mod.npg_bulk_delete_proxy_hosts(host_ids=_many_ids(n)))
        assert result["success"] is True
        assert slow.peak <= _BULK_WRITE_CONCURRENCY
        assert slow.peak > 1
        assert slow.calls == n

    def test_order_preserved_and_isolation(self, slow):
        ids = ["ok-a", "fail-b", "ok-c"]
        result = _run(main_mod.npg_bulk_delete_proxy_hosts(host_ids=ids))
        assert result["success"] is True
        assert [e["host_id"] for e in result["data"]] == ids
        assert [e["success"] for e in result["data"]] == [True, False, True]


class TestBulkRenewCertificatesConcurrency:
    def test_wall_time_bounded_not_sequential(self, slow):
        n = 3 * _BULK_RENEW_CONCURRENCY
        t0 = time.monotonic()
        result = _run(main_mod.npg_bulk_renew_certificates(cert_ids=_many_ids(n, "cert")))
        elapsed = time.monotonic() - t0
        assert result["success"] is True
        assert elapsed < n * _DELAY * 0.6
        assert elapsed >= 3 * _DELAY * 0.9

    def test_peak_concurrency_never_exceeds_acme_cap(self, slow):
        n = 2 * _BULK_RENEW_CONCURRENCY + 2
        result = _run(main_mod.npg_bulk_renew_certificates(cert_ids=_many_ids(n, "cert")))
        assert result["success"] is True
        assert slow.peak <= _BULK_RENEW_CONCURRENCY
        assert slow.peak > 1
        assert slow.calls == n

    def test_order_preserved_and_isolation(self, slow):
        ids = ["ok-cert", "fail-cert", "ok-2"]
        result = _run(main_mod.npg_bulk_renew_certificates(cert_ids=ids))
        assert result["success"] is True
        assert [e["cert_id"] for e in result["data"]] == ids
        assert [e["success"] for e in result["data"]] == [True, False, True]


class TestBulkGetProxyHostFullConcurrency:
    def test_peak_never_exceeds_two_level_cap(self, slow):
        # 50 hosts (the cap) x 11 sections = 550 calls, previously all
        # uncapped. Peak in-flight must stay <= host_cap * section_cap.
        n = _BULK_HOST_LIMIT
        result = _run(
            main_mod.npg_bulk_get_proxy_host_full(host_ids=_many_ids(n))
        )
        assert result["success"] is True
        assert slow.peak <= _BULK_HOST_CONCURRENCY * _BULK_SECTION_CONCURRENCY
        assert slow.peak > 1
        assert slow.calls == n * 11

    def test_order_and_shape_preserved(self, slow):
        ids = _many_ids(25)
        result = _run(main_mod.npg_bulk_get_proxy_host_full(host_ids=ids))
        assert result["success"] is True
        assert list(result["data"].keys()) == ids
        assert result["hosts_failed"] == []
        for hid, entry in result["data"].items():
            assert entry["success"] is True
            assert set(entry["data"].keys()) == set(main_mod._proxy_host_section_paths(hid))
            assert entry["sections_failed"] == []

    def test_failed_host_isolated_not_abort(self, slow):
        ids = ["ok-a", "fail-b", "ok-c"]
        result = _run(main_mod.npg_bulk_get_proxy_host_full(host_ids=ids))
        assert result["success"] is True
        assert result["hosts_failed"] == ["fail-b"]
        assert result["data"]["fail-b"]["success"] is False
        # Healthy hosts still return their full config
        assert result["data"]["ok-a"]["success"] is True
        assert result["data"]["ok-c"]["success"] is True
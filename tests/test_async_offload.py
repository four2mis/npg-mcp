"""Concurrency smoke test: blocking NPGClient calls must not serialize on the event loop.

Every tool wraps its HTTP call in ``_api()`` (asyncio.to_thread). With a fake
client whose GET sleeps ``DELAY`` seconds, N concurrent tool calls must finish
in ~max(DELAY), not ~sum(DELAY) — proving the event loop is free while worker
threads block on I/O.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import npg_mcp.main as main_mod

DELAY = 0.4
CONCURRENCY = 5


class _SlowClient:
    """Fake NPGClient that blocks the calling thread for DELAY seconds."""

    def get(self, path, params=None):
        time.sleep(DELAY)
        return {"path": path}


@pytest.fixture
def slow_client(monkeypatch):
    client = _SlowClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def test_concurrent_tool_calls_overlap(slow_client):
    async def one():
        return await main_mod.npg_get_proxy_host("test-host-id")

    async def _gather():
        return await asyncio.gather(*(one() for _ in range(CONCURRENCY)))

    start = time.monotonic()
    results = asyncio.run(_gather())
    elapsed = time.monotonic() - start

    assert all(r["success"] for r in results)
    # Serialized (old behavior): >= CONCURRENCY * DELAY. Overlapped: < 2 * DELAY.
    upper_bound = 2 * DELAY
    assert elapsed < upper_bound, (
        f"{CONCURRENCY} concurrent calls took {elapsed:.2f}s "
        f"(>={upper_bound:.2f}s would mean the event loop is still blocked)"
    )

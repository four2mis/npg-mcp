"""Unit tests for npg_get_health (GET /health — API origin-root liveness).

Verifies, without any network access:
* the tool issues GET ``/health`` (NOT ``/api/v1/health`` — the liveness
  endpoint is served at the origin root per upstream routes.go and swagger),
* success passthrough returns ``{"success": True, "data": <payload>}``,
* failures surface the standard ``{"success": False, "error", "hint"}``
  envelope (404 / transport / validation),
* the tool takes zero parameters and lands in the read tier
  (``^npg_get`` read-name regex).

Monkeypatches ``npg_mcp.main._get_client`` with a fake — no HTTP happens.
"""

from __future__ import annotations

import asyncio
import inspect

import npg_mcp.client as client_mod
import npg_mcp.main as main_mod
import npg_mcp.toolsets as toolsets_mod


def _run(coro):
    return asyncio.run(coro)


class _RecordingClient:
    """Fake NPGClient that records GET paths and returns a fixed payload."""

    def __init__(self):
        self.calls: list[str] = []
        self._payload = {
            "status": "healthy",
            "database": "ok",
            "cache": "ok",
            "uptime": "1h2m3s",
            "version": "2.58.0",
            "timestamp": "2026-09-25T00:34:42Z",
        }

    def get(self, path, params=None):
        self.calls.append(path)
        return dict(self._payload)


class _DownClient:
    def get(self, path, params=None):
        raise client_mod.NPGError("NPG API request failed")


class _NotFoundClient:
    def get(self, path, params=None):
        raise client_mod.NPGError("NPG API returned HTTP 404")


class TestNpgGetHealth:
    def test_gets_origin_root_health_not_api_v1(self, monkeypatch):
        client = _RecordingClient()
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        result = _run(main_mod.npg_get_health())
        assert result["success"] is True
        assert client.calls == ["/health"]

    def test_success_payload_passthrough(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _RecordingClient())
        result = _run(main_mod.npg_get_health())
        assert result["success"] is True
        assert result["data"]["status"] == "healthy"
        assert result["data"]["version"] == "2.58.0"

    def test_transport_failure_surfaces_error_envelope(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _DownClient())
        result = _run(main_mod.npg_get_health())
        assert result["success"] is False
        assert result["error"] == "NPG API request failed"
        assert result["hint"]

    def test_404_surfaces_error_envelope(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _NotFoundClient())
        result = _run(main_mod.npg_get_health())
        assert result["success"] is False
        assert result["error"] == "NPG API returned HTTP 404"
        assert result["hint"]

    def test_zero_parameters(self):
        sig = inspect.signature(main_mod.npg_get_health)
        assert list(sig.parameters) == []

    def test_lands_in_read_tier(self):
        names = toolsets_mod._discover_tool_names()
        assert "npg_get_health" in names
        allowed = toolsets_mod.tier_allowed(names, "read")
        assert "npg_get_health" in allowed
        # Read-only: must NOT be classified destructive (it would then be
        # excluded from the standard tier, which would be wrong).
        assert "npg_get_health" not in toolsets_mod.DESTRUCTIVE_TOOLS

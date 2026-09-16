"""Unit tests for npg_get_server_info + the error-hint envelope.

Verifies, without any network access:
* ``_error_hint`` maps sanitized exceptions to the expected static hint
  (status classes 400/401/403/404/409/429/5xx, retries, transport, token,
  validation, default) — pure-function behavior,
* ``_error_result`` produces ``{"success": False, "error": ..., "hint": ...}``
  and never leaks upstream detail into the hint,
* ``npg_get_server_info`` composes NPG reachability/version/tool-count and
  degrades gracefully (success + ``npg_reachable: False``) when the NPG API
  is down,
* a sample of tools returns the hint key on failure (shape is additive).

Monkeypatches ``npg_mcp.main._get_client`` with a fake so no HTTP happens.
"""

from __future__ import annotations

import asyncio

import npg_mcp.client as client_mod
import npg_mcp.main as main_mod


def _run(coro):
    return asyncio.run(coro)


class _DownClient:
    """Fake client whose GET always fails (NPG unreachable)."""

    def get(self, path, params=None):
        raise client_mod.NPGError("NPG API request failed")


class _HealthyClient:
    """Fake client returning a /health/detailed payload."""

    def get(self, path, params=None):
        return {"version": "2.55.0", "uptime_seconds": 1, "database": {}}


class TestErrorHintMapping:
    def test_http_400(self):
        e = client_mod.NPGError("NPG API returned HTTP 400", "domain_names is required")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_400

    def test_http_401_403(self):
        for status in (401, 403):
            e = client_mod.NPGError(f"NPG API returned HTTP {status}", "")
            assert main_mod._error_hint(e) == main_mod._ERROR_HINT_401_403

    def test_http_404(self):
        e = client_mod.NPGError("NPG API returned HTTP 404", "")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_404

    def test_http_409(self):
        e = client_mod.NPGError("NPG API returned HTTP 409", "")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_409

    def test_http_429(self):
        e = client_mod.NPGError("NPG API returned HTTP 429", "")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_429

    def test_http_5xx(self):
        for status in (500, 502, 503):
            e = client_mod.NPGError(f"NPG API returned HTTP {status}", "")
            assert main_mod._error_hint(e) == main_mod._ERROR_HINT_5XX

    def test_retries_exhausted(self):
        e = client_mod.NPGError("NPG API request failed after retries")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_RETRIES

    def test_transport_failure(self):
        e = client_mod.NPGError("NPG API request failed")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_TRANSPORT

    def test_missing_token(self):
        e = RuntimeError("NPG_API_TOKEN environment variable not set.")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_TOKEN

    def test_validation_error(self):
        for e in (
            ValueError("host_id is required (got: empty string)"),
            TypeError("bad"),
        ):
            assert main_mod._error_hint(e) == main_mod._ERROR_HINT_INPUT

    def test_default_fallback(self):
        e = RuntimeError("something entirely unexpected")
        assert main_mod._error_hint(e) == main_mod._ERROR_HINT_DEFAULT

    def test_hints_never_contain_upstream_detail(self):
        # The sanitized detail ("upstream secret text") must NOT appear in any
        # hint — hints are static strings keyed by status class only.
        e = client_mod.NPGError("NPG API returned HTTP 400", "upstream secret text")
        result = main_mod._error_result(e)
        assert "upstream secret text" in result["error"]  # detail lives in error only
        assert "upstream secret text" not in result["hint"]


class TestErrorResultShape:
    def test_shape_is_additive(self):
        result = main_mod._error_result(
            client_mod.NPGError("NPG API returned HTTP 404")
        )
        assert result["success"] is False
        assert result["error"] == "NPG API returned HTTP 404"
        assert isinstance(result["hint"], str) and result["hint"]
        assert set(result) == {"success", "error", "hint"}

    def test_sample_tools_emit_hint_on_failure(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _DownClient())
        host_result = _run(main_mod.npg_get_proxy_host("not-a-real-host-id"))
        assert host_result["success"] is False
        assert host_result["hint"]
        list_result = _run(main_mod.npg_list_proxy_hosts())
        assert list_result["success"] is False
        assert list_result["hint"]
        status_result = _run(main_mod.npg_get_status())
        assert status_result["success"] is False
        assert status_result["hint"]


class TestServerInfo:
    def test_success_with_healthy_npg(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _HealthyClient())
        result = _run(main_mod.npg_get_server_info())
        assert result["success"] is True
        data = result["data"]
        assert data["npg_version"] == "2.55.0"
        assert data["npg_reachable"] is True
        assert data["mcp_tool_count"] == len(main_mod.mcp._tool_manager.list_tools())
        assert data["mcp_tool_count"] > 0
        assert isinstance(data["npg_dry_run"], bool)
        assert "api_base_url" in data and data["api_base_url"]

    def test_degrades_gracefully_when_npg_down(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _DownClient())
        result = _run(main_mod.npg_get_server_info())
        assert result["success"] is True
        data = result["data"]
        assert data["npg_version"] is None
        assert data["npg_reachable"] is False
        assert data["mcp_tool_count"] > 0

    def test_no_required_params(self):
        import inspect
        sig = inspect.signature(main_mod.npg_get_server_info)
        assert all(
            p.default is inspect.Parameter.empty is False or p.default is None
            or p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )

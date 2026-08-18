"""Unit tests for the HTTP /health endpoint (npg_mcp.main).

Covers:
* _health_app returns 200 {"status": "ok", "tools", "npg_reachable": true}
  when NPG_API_TOKEN is set and the NPG probe succeeds.
* 503 + JSON error body when the NPG probe fails (NPG unreachable).
* 503 + JSON error body when NPG_API_TOKEN is missing.
* _bearer_auth_middleware lets /health through WITHOUT MCP_API_TOKEN while
  still 401-ing every other path.
* The /health route is NOT an MCP tool (no @mcp.tool registration).

The NPG probe is monkeypatched — no real network access. The probe never
raises and never leaks secrets; the response body never contains a token.
"""

from __future__ import annotations

import pytest

import npg_mcp.main as main_mod

# starlette TestClient drives the ASGI app in-process (httpx-based).
from starlette.testclient import TestClient


@pytest.fixture
def token_env(monkeypatch):
    """Set NPG_API_TOKEN + MCP_API_TOKEN in the environment for a test."""
    monkeypatch.setenv("NPG_API_TOKEN", "ng_test_token")
    monkeypatch.setenv("MCP_API_TOKEN", "mcp_secret")
    return "ng_test_token"


@pytest.fixture
def probe_ok(monkeypatch):
    monkeypatch.setattr(main_mod, "_probe_npg", lambda timeout=3.0: True)


@pytest.fixture
def probe_down(monkeypatch):
    monkeypatch.setattr(main_mod, "_probe_npg", lambda timeout=3.0: False)


class TestHealthApp:
    """The /health route behavior in isolation."""

    def _client(self, exposed_tools=276):
        return TestClient(main_mod._health_app(exposed_tools))

    def test_healthy_returns_200_ok_json(self, token_env, probe_ok):
        with self._client(276) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["tools"] == 276
        assert body["npg_reachable"] is True

    def test_tools_count_reflects_exposed_toolset(self, token_env, probe_ok):
        with self._client(123) as client:
            body = client.get("/health").json()
        assert body["tools"] == 123

    def test_unreachable_npg_returns_503_error_body(self, token_env, probe_down):
        with self._client(276) as client:
            resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "error"
        assert body["tools"] == 276
        assert body["npg_reachable"] is False
        assert body["error"] == "NPG API unreachable"

    def test_missing_token_returns_503_error_body(self, monkeypatch, probe_down):
        # NPG_API_TOKEN unset; MCP_API_TOKEN may be anything.
        monkeypatch.delenv("NPG_API_TOKEN", raising=False)
        monkeypatch.setenv("MCP_API_TOKEN", "mcp_secret")
        with self._client(276) as client:
            resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"] == "NPG_API_TOKEN not configured"

    def test_healthy_body_never_contains_token(self, token_env, probe_ok):
        with self._client(276) as client:
            body = client.get("/health").json()
        assert "ng_test_token" not in str(body)
        assert "mcp_secret" not in str(body)

    def test_only_get_method(self, token_env, probe_ok):
        with self._client(276) as client:
            resp = client.post("/health")
        assert resp.status_code == 405


class TestHealthBypassesBearerAuth:
    """/health must work without MCP_API_TOKEN; all other paths must not."""

    def test_health_allowed_without_token(self, token_env, probe_ok):
        app = main_mod._bearer_auth_middleware(main_mod._health_app(276), "mcp_secret")
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_other_paths_still_require_token(self, token_env, probe_ok):
        app = main_mod._bearer_auth_middleware(main_mod._health_app(276), "mcp_secret")
        with TestClient(app) as client:
            missing = client.get("/mcp")
            with_token = client.get(
                "/mcp", headers={"Authorization": "Bearer mcp_secret"}
            )
        assert missing.status_code == 401
        # /mcp exists in the health app? It does not — 404 proves the request
        # PASSED auth (it reached the app), while 401 proves it was rejected.
        assert with_token.status_code == 404

    def test_health_still_works_when_token_env_missing(self, monkeypatch, probe_ok):
        # The healthcheck container cannot carry MCP_API_TOKEN at all.
        monkeypatch.delenv("NPG_API_TOKEN", raising=False)
        monkeypatch.delenv("MCP_API_TOKEN", raising=False)
        app = main_mod._bearer_auth_middleware(main_mod._health_app(276), "mcp_secret")
        with TestClient(app) as client:
            # probe is faked healthy, but NPG_API_TOKEN is missing → 503 with
            # the "not configured" body — still answered, still no 401.
            resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["error"] == "NPG_API_TOKEN not configured"


class TestHealthIsNotAnMCPTool:
    """The /health route must not appear in the MCP tool surface."""

    def test_health_not_registered_as_mcp_tool(self):
        names = {t.name for t in main_mod.mcp._tool_manager.list_tools()}
        assert "health" not in names
        assert not any("health" == n for n in names)

    def test_tool_count_unchanged(self):
        names = main_mod.mcp._tool_manager.list_tools()
        assert len(names) == 276

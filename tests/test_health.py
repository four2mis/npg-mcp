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

import json
import logging

import httpx
import pytest

import npg_mcp.client as client_mod
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

    def _client(self, exposed_tools=278):
        return TestClient(main_mod._health_app(exposed_tools))

    def test_healthy_returns_200_ok_json(self, token_env, probe_ok):
        with self._client(278) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["tools"] == 278
        assert body["npg_reachable"] is True

    def test_tools_count_reflects_exposed_toolset(self, token_env, probe_ok):
        with self._client(123) as client:
            body = client.get("/health").json()
        assert body["tools"] == 123

    def test_unreachable_npg_returns_503_error_body(self, token_env, probe_down):
        with self._client(278) as client:
            resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "error"
        assert body["tools"] == 278
        assert body["npg_reachable"] is False
        assert body["error"] == "NPG API unreachable"

    def test_missing_token_returns_503_error_body(self, monkeypatch, probe_down):
        # NPG_API_TOKEN unset; MCP_API_TOKEN may be anything.
        monkeypatch.delenv("NPG_API_TOKEN", raising=False)
        monkeypatch.setenv("MCP_API_TOKEN", "mcp_secret")
        with self._client(278) as client:
            resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"] == "NPG_API_TOKEN not configured"

    def test_healthy_body_never_contains_token(self, token_env, probe_ok):
        with self._client(278) as client:
            body = client.get("/health").json()
        assert "ng_test_token" not in str(body)
        assert "mcp_secret" not in str(body)

    def test_only_get_method(self, token_env, probe_ok):
        with self._client(278) as client:
            resp = client.post("/health")
        assert resp.status_code == 405


class TestHealthBypassesBearerAuth:
    """/health must work without MCP_API_TOKEN; all other paths must not."""

    def test_health_allowed_without_token(self, token_env, probe_ok):
        app = main_mod._bearer_auth_middleware(main_mod._health_app(278), "mcp_secret")
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_other_paths_still_require_token(self, token_env, probe_ok):
        app = main_mod._bearer_auth_middleware(main_mod._health_app(278), "mcp_secret")
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
        app = main_mod._bearer_auth_middleware(main_mod._health_app(278), "mcp_secret")
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
        assert len(names) == 288


class TestAccessLogRequestId:
    """_access_log_middleware emits a unique req=<id> per inbound request.

    The ID must appear in BOTH the inbound MCP request log line and — via the
    propagated ContextVar — the outbound NPG API log line, so container logs
    correlate them under concurrent clients. Outside a request (startup,
    stdio, health probe) the ContextVar stays empty and log lines carry no
    req= prefix.
    """

    @staticmethod
    def _make_app(do_api_call: bool):
        """Fake JSON-RPC app: performs one NPGClient.get inside the request
        context when do_api_call (mirroring how tool functions call
        _get_client), then returns 200 with a minimal body."""
        from respx import MockRouter

        async def _app(scope, receive, send):
            body = b""
            while True:
                msg = await receive()
                if msg["type"] == "http.request":
                    body += msg.get("body") or b""
                    if not msg.get("more_body"):
                        break
            payload = json.loads(body) if body else {}
            if do_api_call and payload.get("method") == "tools/call":
                with MockRouter() as router:
                    router.get("https://npg.test/api/v1/hosts").mock(
                        return_value=httpx.Response(200, json={"data": []})
                    )
                    client_mod.NPGClient(base_url="https://npg.test", token="t").get(
                        "/api/v1/hosts"
                    )
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b"{}"})

        return _app

    @staticmethod
    def _make_receive(body: bytes):
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        return receive

    @staticmethod
    def _make_send():
        messages: list[dict] = []

        async def send(message: dict):
            messages.append(message)

        return send, messages

    @staticmethod
    def _request_body(n: int = 1) -> bytes:
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": n,
                "method": "tools/call",
                "params": {"name": "npg_get_proxy_host", "arguments": {}},
            }
        ).encode()

    def test_request_id_in_both_log_lines(self, caplog):
        """A tools/call request logs one MCP line and one NPG line sharing the
        same unique req= prefix."""
        middleware = main_mod._access_log_middleware(self._make_app(do_api_call=True))
        import anyio
        import re

        with caplog.at_level(logging.INFO):
            send, _ = self._make_send()
            anyio.run(
                lambda: middleware(
                    {
                        "type": "http",
                        "method": "POST",
                        "path": "/mcp",
                        "client": ("10.0.0.1", 1234),
                    },
                    self._make_receive(self._request_body()),
                    send,
                )
            )

        records = [r for r in caplog.records if r.name.startswith("npg_mcp")]
        mcp_lines = [r.getMessage() for r in records if "MCP request" in r.getMessage()]
        npg_lines = [r.getMessage() for r in records if r.getMessage().startswith("NPG ")]
        assert mcp_lines, "expected an MCP request log line"
        assert npg_lines, "expected an outbound NPG log line"
        mcp_req = re.search(r"req=(r-[0-9a-f]{8})", mcp_lines[0])
        npg_req = re.search(r"req=(r-[0-9a-f]{8})", npg_lines[0])
        assert mcp_req, f"MCP line missing req=: {mcp_lines[0]}"
        assert npg_req, f"NPG line missing req=: {npg_lines[0]}"
        assert mcp_req.group(1) == npg_req.group(1)
        # MCP line keeps tool name + client + status + duration fields.
        assert "tool=npg_get_proxy_host" in mcp_lines[0]
        assert "client=10.0.0.1" in mcp_lines[0]
        assert "-> 200 (" in mcp_lines[0]

    def test_ids_unique_across_requests(self, caplog):
        """Two sequential requests get different req= IDs."""
        middleware = main_mod._access_log_middleware(self._make_app(do_api_call=True))
        import anyio
        import re

        with caplog.at_level(logging.INFO):
            for n in (1, 2):
                send, _ = self._make_send()
                anyio.run(
                    lambda: middleware(
                        {
                            "type": "http",
                            "method": "POST",
                            "path": "/mcp",
                            "client": ("10.0.0.2", 5678),
                        },
                        self._make_receive(self._request_body(n)),
                        send,
                    )
                )

        mcp_ids = [
            re.search(r"req=(r-[0-9a-f]{8})", r.getMessage()).group(1)
            for r in caplog.records
            if r.name.startswith("npg_mcp") and "MCP request" in r.getMessage()
        ]
        assert len(mcp_ids) == 2
        assert mcp_ids[0] != mcp_ids[1]

    def test_contextvar_reset_after_request(self):
        """After a request completes, the ContextVar is back to empty."""
        middleware = main_mod._access_log_middleware(self._make_app(do_api_call=False))
        import anyio

        send, _ = self._make_send()
        anyio.run(
            lambda: middleware(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/mcp",
                    "client": ("10.0.0.3", 9999),
                },
                self._make_receive(b"{}"),
                send,
            )
        )
        # Both ContextVars (main + client) reset after the request.
        assert main_mod._request_id.get() == ""
        assert client_mod.get_request_id() == ""

    def test_new_request_id_format(self):
        rid = main_mod._new_request_id()
        import re

        assert re.fullmatch(r"r-[0-9a-f]{8}", rid)
        # Random per request — not derived from anything request-specific.
        assert main_mod._new_request_id() != rid

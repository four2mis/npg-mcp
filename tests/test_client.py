"""Unit tests for npg_mcp.client.

Covers:
* NPGError sanitization (HTTP 400 with JSON body includes detail; HTTP 500
  without body returns a generic message; transport errors return a generic
  message and never leak internals).
* Retry logic (GET retries on 502/503/504 and ConnectError; does NOT retry on
  400/401/404; POST/PUT/DELETE never retry).
* Singleton lifecycle (get_singleton returns the same instance; close_singleton
  resets the module-level singleton to None).

Every HTTP call is mocked with respx — there is NO real network access.
"""

from __future__ import annotations

import contextvars
import logging

import httpx
import pytest
import respx

from npg_mcp import client as client_mod
from npg_mcp.client import NPGClient, NPGError

BASE = "https://npg.test"


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """Collapse retry backoff so retry tests never sleep."""
    monkeypatch.setattr(client_mod, "_RETRY_BASE_DELAY", 0)
    monkeypatch.setattr(client_mod, "_MAX_RETRIES", 2)


@pytest.fixture(autouse=True)
def _clean_singleton():
    """Ensure the module-level singleton is reset before/after every test."""
    client_mod.close_singleton()
    yield
    client_mod.close_singleton()


@pytest.fixture
def client():
    return NPGClient(base_url=BASE, token="ng_test_token")


def _status_error(status: int, json_body: dict | None = None, content: bytes | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"{BASE}/api/v1/hosts")
    response = httpx.Response(status, request=request, json=json_body, content=content)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


def _status_error_with_headers(status: int, headers: dict) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"{BASE}/api/v1/hosts")
    response = httpx.Response(status, request=request, headers=headers, json={"message": "rl"})
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


class TestNPGErrorSanitization:
    """HTTP/transport errors must become sanitized NPGErrors — no URLs,
    hostnames, or raw internals leak into the message."""

    def test_http_400_json_message_detail(self, client):
        with respx.mock:
            respx.get(f"{BASE}/api/v1/hosts").mock(
                return_value=httpx.Response(400, json={"message": "domain_names is required"})
            )
            with pytest.raises(NPGError) as ei:
                client.get("/api/v1/hosts")
        err = ei.value
        assert err.message == "NPG API returned HTTP 400"
        assert err.detail == "domain_names is required"
        assert "domain_names is required" in str(err)
        assert BASE not in str(err)

    def test_http_400_error_field_detail(self):
        """NPG also returns {"error": "..."} for some endpoints."""
        err = NPGClient(base_url=BASE, token="t")._sanitize(
            _status_error(400, json_body={"error": "invalid payload"})
        )
        assert err.message == "NPG API returned HTTP 400"
        assert err.detail == "invalid payload"

    def test_http_500_no_body_generic_message(self, client):
        with respx.mock:
            respx.get(f"{BASE}/api/v1/hosts").mock(return_value=httpx.Response(500))
            with pytest.raises(NPGError) as ei:
                client.get("/api/v1/hosts")
        err = ei.value
        # 500 is retryable — after exhausting retries the sanitized error still
        # carries only the status, never a body snippet or traceback.
        assert err.message == "NPG API returned HTTP 500"
        assert err.detail == ""
        assert str(err) == "NPG API returned HTTP 500"

    def test_http_500_non_json_text_snippet(self):
        """Non-JSON bodies are surfaced as a short raw snippet (if any)."""
        err = NPGClient(base_url=BASE, token="t")._sanitize(
            _status_error(500, content=b"Internal Server Error")
        )
        assert err.message == "NPG API returned HTTP 500"
        assert err.detail == "Internal Server Error"

    def test_transport_error_generic_message(self, client):
        with respx.mock:
            respx.get(f"{BASE}/api/v1/hosts").mock(side_effect=httpx.ConnectError("boom"))
            with pytest.raises(NPGError) as ei:
                client.get("/api/v1/hosts")
        err = ei.value
        assert err.message == "NPG API request failed"
        assert err.detail == ""
        # The raw transport error text must not leak into the sanitized error
        assert "boom" not in str(err)
        assert BASE not in str(err)

    def test_sanitize_transport_error_never_leaks_url(self):
        err = NPGClient(base_url=BASE, token="t")._sanitize(httpx.ConnectError("connection refused"))
        assert err.message == "NPG API request failed"
        assert BASE not in str(err)


class TestRetryLogic:
    """GET retries on transient failures; mutations never retry."""

    def test_get_retries_on_502_then_succeeds(self, client):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(
            side_effect=[
                httpx.Response(502, json={"message": "bad gateway"}),
                httpx.Response(200, json={"data": "ok"}),
            ]
        )
        with respx.mock:
            data = client.get("/api/v1/hosts")
            # call counts must be read inside the respx.mock block — respx
            # resets route call state when the block exits.
            assert route.call_count == 2
        assert data == {"data": "ok"}

    @pytest.mark.parametrize("status", [503, 504])
    def test_get_retries_on_503_504(self, client, status):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(
            side_effect=[
                httpx.Response(status, json={"message": "nope"}),
                httpx.Response(200, json={"data": status}),
            ]
        )
        with respx.mock:
            data = client.get("/api/v1/hosts")
            assert route.call_count == 2
        assert data == {"data": status}

    def test_get_retries_on_connect_error(self, client):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(
            side_effect=[
                httpx.ConnectError("connection refused"),
                httpx.Response(200, json={"data": "recovered"}),
            ]
        )
        with respx.mock:
            data = client.get("/api/v1/hosts")
            assert route.call_count == 2
        assert data == {"data": "recovered"}

    @pytest.mark.parametrize("status", [400, 401, 404])
    def test_get_does_not_retry_client_errors(self, client, status):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(return_value=httpx.Response(status, json={"message": "nope"}))
        with respx.mock:
            with pytest.raises(NPGError) as ei:
                client.get("/api/v1/hosts")
            assert route.call_count == 1, f"GET must not retry HTTP {status}"
        assert ei.value.message == f"NPG API returned HTTP {status}"

    def test_get_exhausts_retries_on_persistent_502(self, client):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(return_value=httpx.Response(502, json={}))
        with respx.mock:
            with pytest.raises(NPGError) as ei:
                client.get("/api/v1/hosts")
            # initial attempt + 2 retries (monkeypatched _MAX_RETRIES=2)
            assert route.call_count == 3
        assert ei.value.message == "NPG API returned HTTP 502"

    def test_post_never_retries(self, client):
        route = respx.post(f"{BASE}/api/v1/hosts")
        route.mock(return_value=httpx.Response(503, json={"message": "nope"}))
        with respx.mock:
            with pytest.raises(NPGError) as ei:
                client.post("/api/v1/hosts", {"a": 1})
            assert route.call_count == 1
        assert ei.value.message == "NPG API returned HTTP 503"

    def test_put_never_retries(self, client):
        route = respx.put(f"{BASE}/api/v1/hosts/1")
        route.mock(return_value=httpx.Response(503, json={"message": "nope"}))
        with respx.mock:
            with pytest.raises(NPGError) as ei:
                client.put("/api/v1/hosts/1", {"a": 1})
            assert route.call_count == 1
        assert ei.value.message == "NPG API returned HTTP 503"

    def test_delete_never_retries(self, client):
        route = respx.delete(f"{BASE}/api/v1/hosts/1")
        route.mock(return_value=httpx.Response(503, json={"message": "nope"}))
        with respx.mock:
            with pytest.raises(NPGError) as ei:
                client.delete("/api/v1/hosts/1")
            assert route.call_count == 1
        assert ei.value.message == "NPG API returned HTTP 503"


class TestRateLimit429Retry:
    """GET retries HTTP 429 rate-limit responses, honoring Retry-After."""

    def test_429_is_retryable(self, client):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(
            side_effect=[
                httpx.Response(429, json={"message": "rate limited"}),
                httpx.Response(200, json={"data": "ok"}),
            ]
        )
        with respx.mock:
            data = client.get("/api/v1/hosts")
            assert route.call_count == 2
        assert data == {"data": "ok"}

    def test_429_exhausts_retries_then_sanitized_error(self, client):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(return_value=httpx.Response(429, json={"message": "rl"}))
        with respx.mock:
            with pytest.raises(NPGError) as ei:
                client.get("/api/v1/hosts")
            # initial attempt + 2 retries (monkeypatched _MAX_RETRIES=2)
            assert route.call_count == 3
        assert ei.value.message == "NPG API returned HTTP 429"

    def test_400_still_not_retryable(self, client):
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(return_value=httpx.Response(400, json={"message": "nope"}))
        with respx.mock:
            with pytest.raises(NPGError):
                client.get("/api/v1/hosts")
            assert route.call_count == 1

    def test_retry_delay_uses_numeric_retry_after(self, client):
        exc = _status_error_with_headers(429, {"retry-after": "7"})
        delay = client._retry_delay(0, exc)
        assert delay == 7.0

    def test_retry_delay_clamps_retry_after_to_cap(self, client):
        exc = _status_error_with_headers(429, {"retry-after": "300"})
        delay = client._retry_delay(0, exc)
        assert delay == 10.0  # _RETRY_AFTER_CAP

    def test_retry_delay_falls_back_without_retry_after(self, client, monkeypatch):
        monkeypatch.setattr(client_mod, "_RETRY_BASE_DELAY", 0.5)
        exc = _status_error(429)
        # no header → exponential backoff
        assert client._retry_delay(0, exc) == 0.5
        assert client._retry_delay(1, exc) == 1.0

    def test_retry_delay_non_numeric_retry_after_falls_back(self, client, monkeypatch):
        monkeypatch.setattr(client_mod, "_RETRY_BASE_DELAY", 0.5)
        # HTTP-date form of Retry-After is not supported — use backoff.
        exc = _status_error_with_headers(
            429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}
        )
        assert client._retry_delay(0, exc) == 0.5

    def test_should_retry_429_true_400_false(self, client):
        assert client._should_retry(_status_error(429)) is True
        assert client._should_retry(_status_error(400)) is False
        assert client._should_retry(_status_error(503)) is True

    def test_get_retries_429_honoring_retry_after_header(self, client, caplog):
        # End-to-end: a 429 carrying Retry-After: 0 retries and succeeds;
        # the warning log line notes the rate-limited reason.
        route = respx.get(f"{BASE}/api/v1/hosts")
        route.mock(
            side_effect=[
                httpx.Response(
                    429, headers={"Retry-After": "0"}, json={"message": "slow down"}
                ),
                httpx.Response(200, json={"data": ["host"]}),
            ]
        )
        with caplog.at_level(logging.WARNING, logger="npg_mcp.client"):
            with respx.mock:
                data = client.get("/api/v1/hosts")
                assert route.call_count == 2
        assert data == {"data": ["host"]}
        warn_lines = [r.getMessage() for r in caplog.records if "rate-limited" in r.getMessage()]
        assert warn_lines, "expected a 'rate-limited' retry warning log line"

    def test_post_never_retries_on_429(self, client):
        route = respx.post(f"{BASE}/api/v1/hosts")
        route.mock(return_value=httpx.Response(429, json={"message": "rl"}))
        with respx.mock:
            with pytest.raises(NPGError) as ei:
                client.post("/api/v1/hosts", {"a": 1})
            assert route.call_count == 1
        assert ei.value.message == "NPG API returned HTTP 429"


class TestRequestIdCorrelation:
    """Per-request correlation ID plumbing in npg_mcp.client.

    The ContextVar defaults to "" so code paths outside a request (startup,
    stdio mode, health probe) log without a req= prefix — byte-identical to
    the pre-feature format. When set, outbound NPG log lines carry
    `` req=r-<8 hex>``.
    """

    def test_default_empty_no_suffix(self):
        # Fresh context (no middleware ran) — no req= in log lines.
        assert client_mod.get_request_id() == ""
        assert client_mod._req_suffix() == ""

    def test_set_get_roundtrip(self):
        client_mod.set_request_id("r-1a2b3c4d")
        try:
            assert client_mod.get_request_id() == "r-1a2b3c4d"
        finally:
            client_mod.set_request_id("")

    def test_suffix_formats_with_req_prefix(self):
        client_mod.set_request_id("r-1a2b3c4d")
        try:
            assert client_mod._req_suffix() == " req=r-1a2b3c4d"
        finally:
            client_mod.set_request_id("")

    def test_contextvar_isolated_between_contexts(self):
        # A value set in one context must not leak into another (concurrent
        # requests each get their own id).
        ctx = contextvars.copy_context()

        def _set():
            client_mod.set_request_id("r-abc12345")

        ctx.run(_set)
        # The test's own context is untouched.
        assert client_mod.get_request_id() == ""
        # The forked context still sees its own value.
        assert ctx.run(client_mod.get_request_id) == "r-abc12345"

    def test_log_line_carries_req_suffix_when_set(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="npg_mcp.client"):
            client_mod.set_request_id("r-1a2b3c4d")
            try:
                with respx.mock:
                    respx.get(f"{BASE}/api/v1/hosts").mock(
                        return_value=httpx.Response(200, json={"data": []})
                    )
                    client.get("/api/v1/hosts")
            finally:
                client_mod.set_request_id("")
        messages = [r.getMessage() for r in caplog.records if r.name == "npg_mcp.client"]
        ok_lines = [m for m in messages if m.startswith("NPG GET /api/v1/hosts -> 200")]
        assert ok_lines, f"expected NPG GET success log line, got: {messages}"
        # Existing format preserved — only a req= suffix added.
        assert ok_lines[0].endswith("req=r-1a2b3c4d")

    def test_log_line_unchanged_without_request_id(self, client, caplog):
        # No request context — the log line is byte-identical to the old format
        # (no req= anywhere), so existing log parsers keep working.
        with caplog.at_level(logging.INFO, logger="npg_mcp.client"):
            with respx.mock:
                respx.get(f"{BASE}/api/v1/hosts").mock(
                    return_value=httpx.Response(200, json={"data": []})
                )
                client.get("/api/v1/hosts")
        messages = [r.getMessage() for r in caplog.records if r.name == "npg_mcp.client"]
        ok_lines = [m for m in messages if m.startswith("NPG GET /api/v1/hosts -> 200")]
        assert ok_lines, f"expected NPG GET success log line, got: {messages}"
        assert "req=" not in ok_lines[0]
        # And the core fields (method, path, status, ms) are all present.
        assert "NPG GET /api/v1/hosts -> 200 (" in ok_lines[0]
        assert "ms)" in ok_lines[0]


class TestSingletonLifecycle:
    """The module-level singleton pools one httpx.Client for the process."""

    def test_get_singleton_returns_same_instance(self):
        first = client_mod.get_singleton("ng_tok")
        second = client_mod.get_singleton("ng_tok")
        assert first is second
        assert isinstance(first, NPGClient)

    def test_close_singleton_resets_to_none(self):
        first = client_mod.get_singleton("ng_tok")
        assert client_mod._singleton_client is first
        client_mod.close_singleton()
        assert client_mod._singleton_client is None
        second = client_mod.get_singleton("ng_tok")
        assert second is not first
        assert isinstance(second, NPGClient)


class TestHttpTimeout:
    """NPG_HTTP_TIMEOUT configures the outbound httpx request timeout.

    The value is read once at module import (mirroring the NPG_DRY_RUN
    pattern) and applied to every NPGClient instance. Invalid values fall
    back to 30 with a warning; values outside [1, 600] are clamped.
    """

    def test_client_uses_module_timeout(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_HTTP_TIMEOUT", 60.0)
        c = NPGClient(base_url=BASE, token="t")
        assert c._client.timeout == httpx.Timeout(60.0)

    def test_default_30_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("NPG_HTTP_TIMEOUT", raising=False)
        assert client_mod._load_http_timeout() == 30.0

    def test_env_value_parsed(self, monkeypatch):
        monkeypatch.setenv("NPG_HTTP_TIMEOUT", "60")
        assert client_mod._load_http_timeout() == 60.0

    def test_float_env_value_parsed(self, monkeypatch):
        monkeypatch.setenv("NPG_HTTP_TIMEOUT", "45.5")
        assert client_mod._load_http_timeout() == 45.5

    def test_invalid_value_falls_back_to_default(self, monkeypatch, caplog):
        monkeypatch.setenv("NPG_HTTP_TIMEOUT", "not-a-number")
        with caplog.at_level(logging.WARNING, logger="npg_mcp.client"):
            assert client_mod._load_http_timeout() == 30.0
        assert any("NPG_HTTP_TIMEOUT" in r.getMessage() for r in caplog.records)

    def test_below_min_clamped(self, monkeypatch, caplog):
        monkeypatch.setenv("NPG_HTTP_TIMEOUT", "0.1")
        with caplog.at_level(logging.WARNING, logger="npg_mcp.client"):
            assert client_mod._load_http_timeout() == 1.0
        assert any("clamping" in r.getMessage() for r in caplog.records)

    def test_above_max_clamped(self, monkeypatch, caplog):
        monkeypatch.setenv("NPG_HTTP_TIMEOUT", "9000")
        with caplog.at_level(logging.WARNING, logger="npg_mcp.client"):
            assert client_mod._load_http_timeout() == 600.0
        assert any("clamping" in r.getMessage() for r in caplog.records)

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

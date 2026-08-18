"""NginxProxyGuard API client — thin HTTP wrapper with API token auth."""

from __future__ import annotations

import logging
import os
import time
from contextvars import ContextVar
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("npg_mcp.client")

# Per-request token store — scoped to the current request context var so
# concurrent clients cannot overwrite each other's session token.
_request_token: ContextVar[str] = ContextVar("npg_request_token", default="")
_current_base_url: str = ""

# Module-level singleton client for connection pooling. The env-var token
# path creates a single NPGClient with a persistent httpx.Client connection
# pool, reused across all 274 tool calls instead of opening a new TCP
# connection per request.
_singleton_client: "NPGClient | None" = None

# HTTP status codes eligible for retry (transient server-side failures).
_RETRYABLE_STATUS = frozenset({502, 503, 504})
# Maximum retry attempts for idempotent GET requests.
_MAX_RETRIES = 2
# Base delay in seconds for exponential backoff between retries.
_RETRY_BASE_DELAY = 0.5


def set_token(token: str) -> None:
    """Set the token for the *current* request context (not process-wide)."""
    _request_token.set(token)


def get_token() -> str:
    return _request_token.get()


def set_base_url(base_url: str) -> None:
    global _current_base_url
    _current_base_url = base_url


def get_base_url() -> str:
    return _current_base_url or os.environ.get("NPG_BASE_URL", "http://npg-api:8080")


def get_singleton(token: str) -> "NPGClient":
    """Return (or lazily create) the module-level singleton client.

    The singleton is keyed by the env-var token because that token is static
    for the process lifetime. Per-request ContextVar tokens still get their
    own throwaway client (see ``_get_client`` in main.py).
    """
    global _singleton_client
    if _singleton_client is None:
        _singleton_client = NPGClient(token=token)
    return _singleton_client


def close_singleton() -> None:
    """Close the singleton client (call on shutdown if needed)."""
    global _singleton_client
    if _singleton_client is not None:
        _singleton_client.close()
        _singleton_client = None


class NPGError(Exception):
    """Sanitized error — never contains internal URLs, hostnames, or tracebacks.

    Includes a short snippet of the NPG API error response body (if available)
    so MCP clients can distinguish 400-validation from 404-not-found without
    leaking secrets or internal paths.
    """
    def __init__(self, message: str, detail: str = ""):
        full = f"{message}: {detail}" if detail else message
        super().__init__(full)
        self.message = message
        self.detail = detail


class NPGClient:
    """Thin httpx wrapper over NPG API with bearer token auth.

    Every outbound request is logged (method, path, HTTP status, duration in ms)
    so container logs show what the server is doing and which NPG API calls
    succeed or fail. Tokens, headers, and request/response bodies are never
    logged — only the endpoint path, which maps 1:1 to an MCP tool.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self._token = token or get_token()
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=30,
        )

    def _sanitize(self, exc: Exception) -> NPGError:
        """Convert a transport/HTTP exception into a sanitized NPGError.

        For HTTP errors, extracts a short snippet of the response body (the NPG
        API typically returns a JSON ``message`` or ``error`` field) so the MCP
        client gets actionable context like ``HTTP 400: domain_names is required``
        instead of just ``HTTP 400``. URLs, hostnames, and tracebacks are never
        included.
        """
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            detail = ""
            try:
                body = exc.response.json()
                # NPG error shapes: {"message": "..."} or {"error": "..."} or
                # {"errors": {...}}
                if isinstance(body, dict):
                    detail = str(body.get("message") or body.get("error") or "")
                    if not detail and isinstance(body.get("errors"), dict):
                        detail = str(body["errors"])[:200]
                elif isinstance(body, str):
                    detail = body[:200]
            except Exception:
                # Non-JSON response — use raw text if short enough
                try:
                    raw = exc.response.text[:200]
                    if raw and raw.strip():
                        detail = raw
                except Exception:
                    pass
            return NPGError(f"NPG API returned HTTP {status}", detail)
        return NPGError("NPG API request failed")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _log_ok(self, method: str, path: str, status: int, start: float) -> None:
        ms = (time.perf_counter() - start) * 1000
        logger.info("NPG %s %s -> %s (%d ms)", method, path, status, ms)

    def _log_err(
        self, method: str, path: str, exc: Exception, start: float
    ) -> NPGError:
        """Log an outbound NPG API failure, then return the sanitized error."""
        ms = (time.perf_counter() - start) * 1000
        if isinstance(exc, httpx.HTTPStatusError):
            logger.error(
                "NPG %s %s -> HTTP %s (%d ms)",
                method, path, exc.response.status_code, ms,
            )
        else:
            logger.warning(
                "NPG %s %s -> request failed: %s (%d ms)",
                method, path, type(exc).__name__, ms,
            )
        return self._sanitize(exc)

    def _should_retry(self, exc: Exception) -> bool:
        """Return True if a transient error is eligible for retry."""
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in _RETRYABLE_STATUS
        # Transport-level errors (connect, read, timeout) are also retryable
        return isinstance(
            exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)
        )

    def _retry_delay(self, attempt: int) -> float:
        """Exponential backoff: 0.5s, 1.0s, ..."""
        return _RETRY_BASE_DELAY * (2 ** attempt)

    def get(self, path: str, params: dict | None = None) -> dict | None:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        for attempt in range(_MAX_RETRIES + 1):
            start = time.perf_counter()
            try:
                resp = self._client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                self._log_ok("GET", path, resp.status_code, start)
                if resp.status_code == 204 or not resp.content:
                    return None
                return resp.json()
            except NPGError:
                raise
            except Exception as e:
                if attempt < _MAX_RETRIES and self._should_retry(e):
                    delay = self._retry_delay(attempt)
                    logger.warning(
                        "NPG GET %s -> transient error (%s), retry %d/%d in %.1fs",
                        path, type(e).__name__, attempt + 1, _MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                raise self._log_err("GET", path, e, start) from e
        # Unreachable — loop exits via return or raise
        raise NPGError("NPG API request failed after retries")

    def get_text(self, path: str, params: dict | None = None) -> str:
        """GET returning raw response text (for non-JSON endpoints like log
        downloads)."""
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        for attempt in range(_MAX_RETRIES + 1):
            start = time.perf_counter()
            try:
                resp = self._client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                self._log_ok("GET", path, resp.status_code, start)
                return resp.text
            except NPGError:
                raise
            except Exception as e:
                if attempt < _MAX_RETRIES and self._should_retry(e):
                    delay = self._retry_delay(attempt)
                    logger.warning(
                        "NPG GET %s -> transient error (%s), retry %d/%d in %.1fs",
                        path, type(e).__name__, attempt + 1, _MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                raise self._log_err("GET", path, e, start) from e
        raise NPGError("NPG API request failed after retries")

    def post(
        self, path: str, body: dict | None = None, params: dict | None = None
    ) -> dict | None:
        start = time.perf_counter()
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            resp = self._client.post(
                url, json=body, params=params, headers=self._headers()
            )
            resp.raise_for_status()
            self._log_ok("POST", path, resp.status_code, start)
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._log_err("POST", path, e, start) from e

    def put(
        self, path: str, body: dict | None = None, params: dict | None = None
    ) -> dict | None:
        start = time.perf_counter()
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            resp = self._client.put(
                url, json=body, params=params, headers=self._headers()
            )
            resp.raise_for_status()
            self._log_ok("PUT", path, resp.status_code, start)
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._log_err("PUT", path, e, start) from e

    def delete(self, path: str, params: dict | None = None) -> dict | None:
        start = time.perf_counter()
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            resp = self._client.delete(url, params=params, headers=self._headers())
            resp.raise_for_status()
            self._log_ok("DELETE", path, resp.status_code, start)
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._log_err("DELETE", path, e, start) from e

    def post_file(
        self,
        path: str,
        file_field: str,
        file_content: bytes,
        filename: str,
        extra_fields: dict | None = None,
    ) -> dict | None:
        """POST a multipart file upload (for backup restore, certificate
        upload, etc.)."""
        start = time.perf_counter()
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            files = {file_field: (filename, file_content, "application/octet-stream")}
            resp = self._client.post(
                url, files=files, data=extra_fields, headers=self._headers()
            )
            resp.raise_for_status()
            self._log_ok("POST", path, resp.status_code, start)
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._log_err("POST", path, e, start) from e

    def close(self) -> None:
        self._client.close()

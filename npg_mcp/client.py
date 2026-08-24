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
# Per-request correlation ID — set once per inbound MCP request by the access
# log middleware in main.py and read by NPGClient per-call logging, so each
# inbound request and the outbound NPG API calls it makes share a `req=`
# prefix in container logs. Empty by default: code paths outside a request
# (startup, stdio mode, health probe) log without the prefix, byte-identical
# to the previous format.
_request_id: ContextVar[str] = ContextVar("npg_request_id", default="")
_current_base_url: str = ""

# Module-level singleton client for connection pooling. The env-var token
# path creates a single NPGClient with a persistent httpx.Client connection
# pool, reused across all tool calls instead of opening a new TCP
# connection per request.
_singleton_client: "NPGClient | None" = None

# HTTP status codes eligible for retry (transient server-side failures).
_RETRYABLE_STATUS = frozenset({502, 503, 504})
# Rate-limit responses are also retried (GET-only loop — no mutation replay),
# honoring the server's Retry-After hint when present.
_RATE_LIMIT_STATUS = 429
# Maximum retry attempts for idempotent GET requests.
_MAX_RETRIES = 2
# Base delay in seconds for exponential backoff between retries.
_RETRY_BASE_DELAY = 0.5
# Upper bound on a server-provided Retry-After delay, so a long rate-limit
# window cannot stall the MCP worker for minutes.
_RETRY_AFTER_CAP = 10.0


# ── Dry-run mode ──────────────────────────────────────────────────────
# When NPG_DRY_RUN is set to a truthy value, every mutating call (POST/PUT/
# DELETE/file upload) is intercepted BEFORE it reaches the network: the exact
# request that WOULD have been sent (method, path, JSON body, query params,
# multipart file metadata) is returned as a structured payload and nothing is
# executed. This makes first deployment against a live instance safe by
# construction — run the server with NPG_DRY_RUN=1, exercise the tools, and
# inspect the payloads before switching it off.
#
# Read once at process start so the mode cannot change mid-run. Truthy values
# are the same set as Python's bool() on the stripped string (except literal
# "0"/"false"/"no" which read as False for shell ergonomics).
_DRY_RUN: bool = os.environ.get("NPG_DRY_RUN", "").strip().lower() not in (
    "", "0", "false", "no",
)

# Marker key carried in every dry-run payload so clients can detect the mode
# without pattern-matching on tool names.
DRY_RUN_KEY = "dry_run"


# ── HTTP timeout ────────────────────────────────────────────────────
# Outbound NPG API request timeout in seconds, configurable per deployment
# via NPG_HTTP_TIMEOUT. Several endpoints legitimately take longer than the
# 30s default — large access-log downloads, backup export/restore,
# certificate upload, and full proxy-host syncs — and a deployment may need
# to raise the limit without editing source. Read once at process start so
# the value cannot change mid-run. Invalid values fall back to 30 (with a
# warning); values outside [1, 600] are clamped into range.
_HTTP_TIMEOUT_DEFAULT = 30.0
_HTTP_TIMEOUT_MIN = 1.0
_HTTP_TIMEOUT_MAX = 600.0


def _load_http_timeout() -> float:
    raw = os.environ.get("NPG_HTTP_TIMEOUT", "").strip()
    if not raw:
        return _HTTP_TIMEOUT_DEFAULT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "NPG_HTTP_TIMEOUT=%r is not a number, falling back to %ss",
            raw, _HTTP_TIMEOUT_DEFAULT,
        )
        return _HTTP_TIMEOUT_DEFAULT
    if not _HTTP_TIMEOUT_MIN <= value <= _HTTP_TIMEOUT_MAX:
        logger.warning(
            "NPG_HTTP_TIMEOUT=%r is outside [%s, %s], clamping",
            raw, _HTTP_TIMEOUT_MIN, _HTTP_TIMEOUT_MAX,
        )
        return min(_HTTP_TIMEOUT_MAX, max(_HTTP_TIMEOUT_MIN, value))
    return value


_HTTP_TIMEOUT: float = _load_http_timeout()


def dry_run_enabled() -> bool:
    """Return True when NPG_DRY_RUN is enabled for this process."""
    return _DRY_RUN


def _dry_run_payload(method: str, path: str, body=None, params=None) -> dict:
    """Build the structured payload returned instead of a real mutation.

    Body and query params are passed through exactly as the tool built them
    (including ``None`` when the call had no body), so a caller can inspect
    the precise request that WOULD have been sent. PII-sensitive bodies
    (file uploads) are summarized rather than echoed: only the multipart
    field name, file name, and byte size are reported, never the bytes.
    """
    payload: dict = {DRY_RUN_KEY: True, "method": method, "path": path}
    if body is not None:
        payload["body"] = body
    if params:
        payload["params"] = params
    return payload


def _is_rate_limited(exc: Exception) -> bool:
    """Return True if the exception is an HTTP 429 rate-limit response."""
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code == _RATE_LIMIT_STATUS
    )


def set_token(token: str) -> None:
    """Set the token for the *current* request context (not process-wide)."""
    _request_token.set(token)


def get_token() -> str:
    return _request_token.get()


def set_request_id(request_id: str) -> None:
    """Set the correlation ID for the *current* request context (not process-wide)."""
    _request_id.set(request_id)


def get_request_id() -> str:
    """Return the correlation ID for the current request context.

    Returns "" outside a request (startup, stdio mode, health probe).
    """
    return _request_id.get()


def _req_suffix() -> str:
    """Correlation-ID suffix for outbound NPG log lines.

    Returns `` req=r-1a2b3c4d`` when a request correlation ID is set for the
    current context, otherwise "" — keeping log lines outside a request
    (startup, stdio mode, health probe) byte-identical to the pre-feature
    format. Used by NPGClient per-call logging so each inbound MCP request
    and the NPG API calls it triggers share the same ``req=`` prefix.
    """
    rid = _request_id.get()
    return f" req={rid}" if rid else ""


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
            timeout=_HTTP_TIMEOUT,
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
        logger.info(
            "NPG %s %s -> %s (%d ms)%s",
            method, path, status, ms, _req_suffix(),
        )

    def _log_err(
        self, method: str, path: str, exc: Exception, start: float
    ) -> NPGError:
        """Log an outbound NPG API failure, then return the sanitized error."""
        ms = (time.perf_counter() - start) * 1000
        if isinstance(exc, httpx.HTTPStatusError):
            logger.error(
                "NPG %s %s -> HTTP %s (%d ms)%s",
                method, path, exc.response.status_code, ms, _req_suffix(),
            )
        else:
            logger.warning(
                "NPG %s %s -> request failed: %s (%d ms)%s",
                method, path, type(exc).__name__, ms, _req_suffix(),
            )
        return self._sanitize(exc)

    def _should_retry(self, exc: Exception) -> bool:
        """Return True if a transient error is eligible for retry."""
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            return (
                status in _RETRYABLE_STATUS or status == _RATE_LIMIT_STATUS
            )
        # Transport-level errors (connect, read, timeout) are also retryable
        return isinstance(
            exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)
        )

    def _retry_delay(self, attempt: int, exc: Exception | None = None) -> float:
        """Delay before the next retry attempt.

        For 429 rate-limit responses with a numeric ``Retry-After`` header,
        use that value (clamped to _RETRY_AFTER_CAP). Otherwise fall back to
        exponential backoff: 0.5s, 1.0s, ...
        """
        if (
            exc is not None
            and isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code == _RATE_LIMIT_STATUS
        ):
            raw = exc.response.headers.get("retry-after", "")
            try:
                return min(float(raw.strip()), _RETRY_AFTER_CAP)
            except (TypeError, ValueError):
                pass  # missing / non-numeric Retry-After — use backoff
        return _RETRY_BASE_DELAY * (2 ** attempt)

    def get(
        self,
        path: str,
        params: dict | None = None,
        redirect_ok: bool = False,
    ) -> dict | None:
        """GET returning parsed JSON (or None on 204/empty body).

        ``redirect_ok=True`` treats 3xx responses as a normal outcome: the
        Location header is returned as ``{"redirect_url": ...}`` instead of
        raising (used by npg_auth_sso_start, whose endpoint answers with a
        302 to the identity provider). Redirects are never followed so the
        API token is never forwarded to an external IdP.
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        for attempt in range(_MAX_RETRIES + 1):
            start = time.perf_counter()
            try:
                resp = self._client.get(url, params=params, headers=self._headers())
                if resp.status_code in (301, 302, 303, 307, 308) and redirect_ok:
                    self._log_ok("GET", path, resp.status_code, start)
                    location = resp.headers.get("location")
                    return (
                        {"redirect_url": location} if location else None
                    )
                resp.raise_for_status()
                self._log_ok("GET", path, resp.status_code, start)
                if resp.status_code == 204 or not resp.content:
                    return None
                return resp.json()
            except NPGError:
                raise
            except Exception as e:
                if attempt < _MAX_RETRIES and self._should_retry(e):
                    delay = self._retry_delay(attempt, e)
                    reason = (
                        "rate-limited" if _is_rate_limited(e) else "transient error"
                    )
                    logger.warning(
                        "NPG GET %s -> %s (%s), retry %d/%d in %.1fs",
                        path, reason, type(e).__name__,
                        attempt + 1, _MAX_RETRIES, delay,
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
                    delay = self._retry_delay(attempt, e)
                    reason = (
                        "rate-limited" if _is_rate_limited(e) else "transient error"
                    )
                    logger.warning(
                        "NPG GET %s -> %s (%s), retry %d/%d in %.1fs",
                        path, reason, type(e).__name__,
                        attempt + 1, _MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                raise self._log_err("GET", path, e, start) from e
        raise NPGError("NPG API request failed after retries")

    def post(
        self, path: str, body: dict | None = None, params: dict | None = None
    ) -> dict | None:
        if _DRY_RUN:
            return _dry_run_payload("POST", path, body, params)
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
        if _DRY_RUN:
            return _dry_run_payload("PUT", path, body, params)
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
        if _DRY_RUN:
            return _dry_run_payload("DELETE", path, None, params)
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
        if _DRY_RUN:
            payload = _dry_run_payload("POST", path, None, None)
            payload["multipart"] = {
                "field": file_field,
                "filename": filename,
                "size_bytes": len(file_content),
            }
            if extra_fields:
                payload["multipart"]["extra_fields"] = extra_fields
            return payload
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

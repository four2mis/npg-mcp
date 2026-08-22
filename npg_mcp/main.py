"""NginxProxyGuard MCP server — streamable-http transport."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import time
import warnings
from contextvars import ContextVar
from typing import Any, Literal
from urllib.parse import quote

# Suppress MCP SDK v1.x pydantic-settings warning for unresolved forward
# reference in FastMCP.lifespan — harmless, fixed in MCP SDK 2.x
warnings.filterwarnings(
    "ignore",
    message=".*lifespan.*incomplete definition.*",
    category=UserWarning,
    module="pydantic_settings",
)

import httpx  # noqa: E402  (third-party import after filterwarnings setup)
from mcp.server import transport_security  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

import npg_mcp.client as client_mod  # noqa: E402
import npg_mcp.toolsets as toolsets  # noqa: E402

logger = logging.getLogger("npg_mcp.main")

# Context variable for per-request token (future use)
_current_token: ContextVar[str] = ContextVar("npg_token", default="")

# Context variable for the per-request correlation ID. Set once per inbound
# MCP request by _access_log_middleware; consumed by NPGClient per-call
# logging so inbound request lines and their outbound NPG API lines share a
# unique req=r-<8 hex> prefix. Default "" keeps code paths outside a request
# (startup, stdio transport, /health probe) logging cleanly without it.
_request_id: ContextVar[str] = ContextVar("npg_request_id", default="")


def _setup_logging() -> None:
    """Configure stdlib logging for container output.

    Level is controlled by NPG_LOG_LEVEL (default INFO). INFO logs one line per
    inbound MCP request (RPC method, tool name, client IP, status, duration) and
    one line per outbound NPG API call. DEBUG surfaces library-level detail
    (uvicorn, mcp SDK, httpx) on top of the structured lines.
    """
    level_name = os.environ.get("NPG_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        # force=True replaces the plain "%(message)s" handler that FastMCP
        # installs at import time, so our timestamped format is used.
        force=True,
    )
    if level > logging.DEBUG:
        # These libraries log one INFO line per request/session, duplicating
        # our structured MCP request + NPG API lines. Keep >= WARNING unless
        # the user explicitly opts into DEBUG.
        for noisy in (
            "httpx",
            "httpcore",
            "sse_starlette.sse",
            "mcp.server.lowlevel.server",
            "mcp.server.streamable_http",
        ):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def _request_note(body: bytes) -> str:
    """Extract a short RPC/tool identifier from a JSON-RPC body for log lines.

    Only the JSON-RPC method and the tool name are read; argument payloads,
    headers, and tokens are never logged. Returns "" when the body is not
    parseable JSON-RPC.
    """
    if not body:
        return ""
    try:
        data = json.loads(body[:65536].decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    rpc = data.get("method")
    if rpc == "tools/call":
        params = data.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        if isinstance(name, str):
            return f" tool={name}"
        return " rpc=tools/call"
    if isinstance(rpc, str):
        return f" rpc={rpc}"
    return ""


def _new_request_id() -> str:
    """Generate a fresh, collision-resistant per-request correlation ID.

    Format ``r-<8 hex chars>`` — short enough for easy scanning in container
    logs, random enough that concurrent clients never share one. Derived from
    ``secrets.token_hex`` (NOT from any request content, token, or payload),
    so it never leaks sensitive material and appears only in log lines.
    """
    return f"r-{secrets.token_hex(4)}"


def _access_log_middleware(app):
    """Log one line per inbound HTTP request to the MCP endpoint.

    Each line carries the HTTP method/path, the JSON-RPC method and tool name
    (when the body is JSON-RPC), the client IP, the response status, and the
    duration — so users can debug what requests the server is getting and where
    they failed. A unique per-request correlation ID (``req=r-<8 hex>``) is
    generated for every inbound request and propagated through a ContextVar,
    so outbound NPG API calls made by the same request share the same
    ``req=`` prefix in their log lines. The request body is only snapshotted
    for tool-name extraction and forwarded to the app unchanged; headers,
    tokens, and argument payloads are never logged. Unhandled exceptions are
    logged with a traceback.
    """

    async def _middleware(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client") or ("", 0)
        client_ip = str(client[0] or "")

        chunks: list[bytes] = []

        async def _tee_receive():
            message = await receive()
            if message["type"] == "http.request" and message.get("body"):
                chunks.append(message["body"])
            return message

        status = {"code": 0}
        start = time.perf_counter()

        async def _send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        # One correlation ID per inbound request, propagated through the
        # ContextVar so NPGClient per-call logging emits the same req= prefix.
        request_id = _new_request_id()
        _request_id.set(request_id)
        client_mod.set_request_id(request_id)
        try:
            await app(scope, _tee_receive, _send)
        except Exception:
            ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "MCP request %s %s req=%s client=%s -> unhandled error (%d ms)",
                method, path, request_id, client_ip, ms,
            )
            raise
        else:
            ms = (time.perf_counter() - start) * 1000
            note = _request_note(b"".join(chunks))
            logger.info(
                "MCP request %s %s%s req=%s client=%s -> %s (%d ms)",
                method, path, note, request_id, client_ip, status["code"] or "?", ms,
            )
        finally:
            _request_id.set("")
            client_mod.set_request_id("")

    return _middleware


def _probe_npg(timeout: float = 3.0) -> bool:
    """Return True when the NPG API is reachable with the configured token.

    Uses a short-lived throwaway httpx client (NOT the pooled singleton, whose
    30s timeout would block health checks) to GET /api/v1/settings — a
    lightweight, side-effect-free endpoint that proves the NPG base URL is
    reachable and the API token is accepted. Any transport/HTTP error (NPG
    down, wrong URL, missing/expired token) is caught and reported as False;
    this function never raises. The probe path never logs tokens or secrets.
    """
    try:
        client = httpx.Client(
            base_url=client_mod.get_base_url(),
            timeout=timeout,
            follow_redirects=True,
        )
        try:
            token = os.environ.get("NPG_API_TOKEN", "").strip()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            resp = client.get("/api/v1/settings", headers=headers)
            return resp.status_code < 500
        finally:
            client.close()
    except Exception:
        return False


def _health_app(exposed_tools: int):
    """Build a minimal Starlette app exposing the unauthenticated /health route.

    The route reports whether the MCP server is initialized (tool count after
    configure_toolset), whether NPG_API_TOKEN is configured, and whether the
    NPG API is reachable. It is a plain HTTP route — NOT an MCP tool — and is
    mounted OUTSIDE the bearer-auth middleware so a healthcheck can call it
    without carrying MCP_API_TOKEN. stdio transport never builds this app.
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse

    async def _health(request) -> JSONResponse:
        token_ok = bool(os.environ.get("NPG_API_TOKEN", "").strip())
        reachable = _probe_npg()
        if not token_ok or not reachable:
            return JSONResponse(
                {
                    "status": "error",
                    "tools": exposed_tools,
                    "npg_reachable": reachable,
                    "error": (
                        "NPG_API_TOKEN not configured"
                        if not token_ok
                        else "NPG API unreachable"
                    ),
                },
                status_code=503,
            )
        return JSONResponse(
            {"status": "ok", "tools": exposed_tools, "npg_reachable": True}
        )

    app = Starlette()
    app.add_route("/health", _health, methods=["GET"])
    return app


def _load_transport_security() -> transport_security.TransportSecuritySettings:
    """Build scoped transport-security settings from env config.

    Restricts which Host headers and Origins the MCP endpoint will accept,
    and keeps DNS-rebinding protection enabled by default. Configure via:
      - MCP_ALLOWED_HOSTS   comma-separated "host:port" (e.g. "localhost:8081,proxy.example.com:443")
      - MCP_ALLOWED_ORIGINS comma-separated origins (e.g. "https://proxy.example.com")
      - MCP_REBINDING_PROTECTION  "true"/"false" (default true)
    """
    default_hosts = [
        f"127.0.0.1:{os.environ.get('MCP_PORT', '8081')}",
        f"localhost:{os.environ.get('MCP_PORT', '8081')}",
    ]
    hosts = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    if hosts:
        host_list = [h.strip() for h in hosts.split(",") if h.strip()]
    else:
        host_list = list(default_hosts)

    origins = os.environ.get("MCP_ALLOWED_ORIGINS", "").strip()
    origin_list = [o.strip() for o in origins.split(",") if o.strip()] if origins else []

    rebinding = os.environ.get("MCP_REBINDING_PROTECTION", "true").lower() not in ("false", "0", "no")

    return transport_security.TransportSecuritySettings(
        enable_dns_rebinding_protection=rebinding,
        allowed_hosts=host_list,
        allowed_origins=origin_list,
    )


mcp = FastMCP(
    name="npg-mcp",
    instructions="Manage NginxProxyGuard reverse proxy hosts, certificates, and nginx configuration.",
    stateless_http=True,
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8081")),
    transport_security=_load_transport_security(),
)


def _get_client() -> client_mod.NPGClient:
    """Get NPG client authenticated with an API token.

    Auth priority (highest first):
    1. NPG_API_TOKEN env var — long-lived API token (ng_... format).
       Immune to password changes; preferred for production.
       Uses a module-level singleton client with a persistent httpx connection
       pool, reused across all tool calls instead of opening a new TCP
       connection per request.
    2. Per-request ContextVar token (set by MCP middleware).
       Creates a throwaway client (the token changes per request).
    """
    # 1. Long-lived API token — use pooled singleton
    api_token = os.environ.get("NPG_API_TOKEN", "").strip()
    if api_token:
        return client_mod.get_singleton(api_token)

    # 2. Per-request token from ContextVar — fresh client each time
    token = client_mod.get_token()
    if token:
        return client_mod.NPGClient(token=token)

    raise RuntimeError(
        "NPG_API_TOKEN environment variable not set."
    )


def _id_path(id_val) -> str:
    """Convert an ID (int or str) to a string for URL path interpolation."""
    return str(id_val)


# Local-variable names that must never leak into an API request body.
_INTERNAL_BODY_KEYS = frozenset({"self", "c", "body"})

# Hard cap on host_ids per bulk call. A bulk tool replaces N sequential MCP
# calls — it is not meant to sweep the whole inventory in one shot, so any
# call asking for more than this is rejected outright (ValueError) instead of
# being partially executed.
_BULK_HOST_LIMIT = 50

# Hard cap on cert_ids per bulk renewal call. Renewals hit Let's Encrypt/ACME
# rate limits, so batches stay far below the 50-host bulk cap to avoid
# exhausting quotas for the whole deployment.
_BULK_CERT_LIMIT = 20


def _build_body(vars_dict: dict, mapping: dict, id_fields: set | None = None) -> dict:
    """Build an API request body dict from local variables, keeping only non-None values.

    Eliminates the repeated ``if x is not None: body["api_field"] = x`` pattern
    across create/update tools. ``mapping`` is a dict of local-variable name ->
    API field name. Internal keys (``self``/``c``/``body``), values that are
    None, and variables absent from ``vars_dict`` are skipped. All other values
    are passed through unchanged (including list[str] and list[dict] params),
    except fields listed in ``id_fields`` which are coerced via ``_id_path``
    (int -> str, matching URL path interpolation semantics).
    """
    body: dict = {}
    id_fields = id_fields or set()
    for var_name, api_field in mapping.items():
        if var_name in _INTERNAL_BODY_KEYS:
            continue
        if var_name not in vars_dict:
            continue
        value = vars_dict[var_name]
        if value is None:
            continue
        if var_name in id_fields:
            body[api_field] = _id_path(value)
        else:
            body[api_field] = value
    return body


def _validate_id(name: str, value) -> None:
    """Validate a required ID parameter before any API call is made.

    Accepts a positive integer or a non-empty string (UUIDs, slugs, etc.).
    Raises ValueError with a clear message — each tool's ``except Exception``
    block catches it and returns ``{"success": False, "error": str(e)}``.
    This runs BEFORE ``_get_client()`` so no connection is wasted on bad input.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} is required (got: empty string)")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{name} is required (got: {value!r})")
    if isinstance(value, int) and value <= 0:
        raise ValueError(f"{name} is required (got: {value!r})")


def _validate_required(name: str, value) -> None:
    """Validate a required (non-ID) parameter before any API call is made.

    Rejects None, empty strings, empty lists, and empty dicts. Non-empty
    values of any type pass through. Raises ValueError (caught by each tool's
    ``except Exception`` block) with a clear message.
    """
    if value is None:
        raise ValueError(f"{name} is required (got: empty string)")
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"{name} is required (got: empty string)")
    elif isinstance(value, (list, dict)) and len(value) == 0:
        raise ValueError(f"{name} is required (got: empty string)")


def _validate_query_int(name: str, value: int | None) -> None:
    """Validate an optional pagination/filter integer query param.

    None is allowed (param omitted from the query string); a value must be
    a non-negative integer (negative limits/offsets/pages are invalid and
    would otherwise surface as an opaque HTTP 400/500 from the API).
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a non-negative integer (got: {value!r})")
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer (got: {value!r})")


def _list_params(limit: int | None, offset: int | None = None, page: int | None = None) -> dict:
    """Build a GET query-params dict from provided pagination values only.

    Naming follows the swagger contract (page/limit/offset); the running NPG
    fork's proxy-hosts and logs endpoints honor ``per_page`` (page size) and
    ``page`` instead of ``limit``/``offset``, so callers of this helper must
    remap: ``limit`` -> ``per_page`` and ``offset`` -> ``page`` (offset // page
    size + 1) before/after calling it where the fork differs. audit-logs and
    system-logs honor ``limit``/``offset`` directly.
    """
    params: dict = {}
    if page is not None:
        _validate_query_int("page", page)
        params["page"] = page
    if limit is not None:
        _validate_query_int("limit", limit)
        params["limit"] = limit
    if offset is not None:
        _validate_query_int("offset", offset)
        params["offset"] = offset
    return params


def _list_params_per_page(limit: int | None = None, offset: int | None = None, page: int | None = None) -> dict:
    """Like ``_list_params`` but maps to the running fork's ``per_page``/``page``
    scheme used by /proxy-hosts and /logs: ``limit`` becomes ``per_page`` and
    ``offset`` becomes ``page = offset // page_size + 1`` (default size 50).
    """
    params: dict = {}
    if page is not None:
        _validate_query_int("page", page)
        params["page"] = page
    if limit is not None:
        _validate_query_int("limit", limit)
        params["per_page"] = limit
    if offset is not None:
        _validate_query_int("offset", offset)
        page_size = limit if limit is not None else 50
        params["page"] = (offset // page_size) + 1
    return params


# ── Proxy Hosts ───────────────────────────────────────────────────────

@mcp.tool(name="npg_list_proxy_hosts", description="LIST proxy hosts. Optional: page, limit (page size, mapped to API per_page), search (matches domain/forward host text). Paginated responses include pagination metadata (total, page, per_page, total_pages). REQUIRED: none — zero-arg call returns the full (unpaginated) list.")
async def npg_list_proxy_hosts(
    page: int | None = None,
    limit: int | None = None,
    search: str | None = None,
) -> dict:
    c = _get_client()
    try:
        params = _list_params_per_page(limit=limit, page=page)
        if search is not None and str(search).strip():
            params["search"] = str(search)
        data = c.get("/api/v1/proxy-hosts", params=params or None)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host", description="Get a single proxy host by its ID. REQUIRED: host_id.")
async def npg_get_proxy_host(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_by_domain", description="Get a proxy host by its domain name.")
async def npg_get_proxy_host_by_domain(domain: str) -> dict:
    try:
        _validate_required("domain", domain)
        c = _get_client()
        encoded = quote(domain, safe="")
        data = c.get(f"/api/v1/proxy-hosts/by-domain/{encoded}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_proxy_host", description="CREATE a reverse proxy. REQUIRED: domain_names, forward_host, forward_port. Omitted fields inherit global defaults; hardcoded true: enabled, ssl_forced, ssl_http2, block_exploits, waf_use_global; proxy_type='http'. Others: ssl, cache, timeouts, buffering, access, auth, ddns, stream_*.")
async def npg_create_proxy_host(
    domain_names: list[str],
    forward_host: str,
    forward_port: int,
    forward_scheme: str | None = None,
    block_normal: bool | None = None,
    waf_enabled: bool | None = None,
    block_http: bool | None = None,
    ssl_enabled: bool = True,
    ssl_forced: bool = True,
    ssl_http2: bool = True,
    ssl_http3: bool | None = None,
    ssl_cert_id: str | int | None = None,
    cache_enabled: bool | None = None,
    cache_static_only: bool | None = None,
    cache_ttl: str | None = None,
    cache_template: str | None = None,
    advanced_config: str | None = None,
    enable_proxy_headers: bool | None = None,
    host_header: str | None = None,
    extra_domains: list[str] | None = None,
    block_exploits: bool = True,
    block_exploits_exceptions: str | None = None,
    allow_websocket_upgrade: bool = True,
    waf_use_global: bool = True,
    waf_paranoia_level: int | None = None,
    waf_anomaly_threshold: int | None = None,
    waf_mode: str | None = None,
    proxy_connect_timeout: int | None = None,
    proxy_send_timeout: int | None = None,
    proxy_read_timeout: int | None = None,
    proxy_buffering: str | None = None,
    proxy_request_buffering: str | None = None,
    client_max_body_size: str | None = None,
    proxy_max_temp_file_size: str | None = None,
    access_list_id: str | int | None = None,
    auth_provider_id: str | int | None = None,
    auth_bypass_paths: list[str] | None = None,
    ddns_enabled: bool | None = None,
    ddns_provider_id: str | int | None = None,
    ddns_proxied: bool | None = None,
    forward_container_name: str | None = None,
    forward_container_network: str | None = None,
    proxy_type: str = "http",
    enabled: bool = True,
    stream_listen_host: str | None = None,
    stream_listen_port: int | None = None,
    stream_protocol: str = "tcp",
    stream_ssl_preread: bool | None = None,
    stream_accept_proxy_protocol: bool | None = None,
    stream_send_proxy_protocol: bool | None = None,
    stream_proxy_connect_timeout: int | None = None,
    stream_proxy_timeout: int | None = None,
) -> dict:
    try:
        _validate_required("domain_names", domain_names)
        _validate_required("forward_host", forward_host)
        _validate_required("forward_port", forward_port)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "domain_names": "domain_names",
                "forward_host": "forward_host",
                "forward_port": "forward_port",
                "forward_scheme": "forward_scheme",
                "block_normal": "block_normal_access",
                "waf_enabled": "waf_enabled",
                "block_http": "block_http_requests",
                "ssl_enabled": "ssl_enabled",
                "ssl_forced": "ssl_force_https",
                "ssl_http2": "ssl_http2",
                "ssl_http3": "ssl_http3",
                "ssl_cert_id": "certificate_id",
                "cache_enabled": "cache_enabled",
                "cache_static_only": "cache_static_only",
                "cache_ttl": "cache_ttl",
                "cache_template": "cache_template",
                "advanced_config": "advanced_config",
                "enable_proxy_headers": "enable_proxy_headers",
                "host_header": "pass_host_header",
                "extra_domains": "extra_domains",
                "block_exploits": "block_exploits",
                "block_exploits_exceptions": "block_exploits_exceptions",
                "allow_websocket_upgrade": "allow_websocket_upgrade",
                "waf_use_global": "waf_use_global",
                "waf_paranoia_level": "waf_paranoia_level",
                "waf_anomaly_threshold": "waf_anomaly_threshold",
                "waf_mode": "waf_mode",
                "proxy_connect_timeout": "proxy_connect_timeout",
                "proxy_send_timeout": "proxy_send_timeout",
                "proxy_read_timeout": "proxy_read_timeout",
                "proxy_buffering": "proxy_buffering",
                "proxy_request_buffering": "proxy_request_buffering",
                "client_max_body_size": "client_max_body_size",
                "proxy_max_temp_file_size": "proxy_max_temp_file_size",
                "access_list_id": "access_list_id",
                "auth_provider_id": "auth_provider_id",
                "auth_bypass_paths": "auth_bypass_paths",
                "ddns_enabled": "ddns_enabled",
                "ddns_provider_id": "ddns_provider_id",
                "ddns_proxied": "ddns_proxied",
                "forward_container_name": "forward_container_name",
                "forward_container_network": "forward_container_network",
                "proxy_type": "proxy_type",
                "enabled": "enabled",
                "stream_listen_host": "stream_listen_host",
                "stream_listen_port": "stream_listen_port",
                "stream_protocol": "stream_protocol",
                "stream_ssl_preread": "stream_ssl_preread",
                "stream_accept_proxy_protocol": "stream_accept_proxy_protocol",
                "stream_send_proxy_protocol": "stream_send_proxy_protocol",
                "stream_proxy_connect_timeout": "stream_proxy_connect_timeout",
                "stream_proxy_timeout": "stream_proxy_timeout",
            },
            id_fields={"access_list_id", "auth_provider_id", "ddns_provider_id"},
        )

        data = c.post("/api/v1/proxy-hosts", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host", description="UPDATE a proxy host (partial update - only passed fields change). REQUIRED: host_id. skip_nginx=true skips nginx regen. Nullable ids (certificate_id, access_list_id, auth_provider_id, ddns_provider_id, forward container name/network): '' clears, omitted leaves; auth_bypass_paths: [] clears.")
async def npg_update_proxy_host(
    host_id: str | int,
    domain_names: list[str] | None = None,
    forward_host: str | None = None,
    forward_port: int | None = None,
    forward_scheme: str | None = None,
    block_normal: bool | None = None,
    waf_enabled: bool | None = None,
    waf_use_global: bool | None = None,
    waf_paranoia_level: int | None = None,
    waf_anomaly_threshold: int | None = None,
    block_http: bool | None = None,
    ssl_forced: bool | None = None,
    ssl_cert_id: str | int | None = None,
    cache_enabled: bool | None = None,
    cache_static_only: bool | None = None,
    cache_ttl: str | None = None,
    cache_template: str | None = None,
    advanced_config: str | None = None,
    enable_proxy_headers: bool | None = None,
    host_header: str | None = None,
    extra_domains: list[str] | None = None,
    enabled: bool | None = None,
    ssl_http2: bool | None = None,
    ssl_http3: bool | None = None,
    block_exploits: bool | None = None,
    block_exploits_exceptions: str | None = None,
    allow_websocket_upgrade: bool | None = None,
    proxy_connect_timeout: int | None = None,
    proxy_send_timeout: int | None = None,
    proxy_read_timeout: int | None = None,
    proxy_buffering: str | None = None,
    proxy_request_buffering: str | None = None,
    client_max_body_size: str | None = None,
    proxy_max_temp_file_size: str | None = None,
    access_list_id: str | int | None = None,
    auth_provider_id: str | int | None = None,
    auth_bypass_paths: list[str] | None = None,
    ddns_enabled: bool | None = None,
    ddns_provider_id: str | int | None = None,
    ddns_proxied: bool | None = None,
    forward_container_name: str | None = None,
    forward_container_network: str | None = None,
    skip_nginx: bool = False,
) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "domain_names": "domain_names",
                "forward_host": "forward_host",
                "forward_port": "forward_port",
                "forward_scheme": "forward_scheme",
                "block_normal": "block_normal_access",
                "waf_enabled": "waf_enabled",
                "waf_use_global": "waf_use_global",
                "waf_paranoia_level": "waf_paranoia_level",
                "waf_anomaly_threshold": "waf_anomaly_threshold",
                "block_http": "block_http_requests",
                "ssl_forced": "ssl_force_https",
                "ssl_cert_id": "certificate_id",
                "cache_enabled": "cache_enabled",
                "cache_static_only": "cache_static_only",
                "cache_ttl": "cache_ttl",
                "cache_template": "cache_template",
                "advanced_config": "advanced_config",
                "enable_proxy_headers": "enable_proxy_headers",
                "host_header": "pass_host_header",
                "extra_domains": "extra_domains",
                "enabled": "enabled",
                "ssl_http2": "ssl_http2",
                "ssl_http3": "ssl_http3",
                "block_exploits": "block_exploits",
                "block_exploits_exceptions": "block_exploits_exceptions",
                "allow_websocket_upgrade": "allow_websocket_upgrade",
                "proxy_connect_timeout": "proxy_connect_timeout",
                "proxy_send_timeout": "proxy_send_timeout",
                "proxy_read_timeout": "proxy_read_timeout",
                "proxy_buffering": "proxy_buffering",
                "proxy_request_buffering": "proxy_request_buffering",
                "client_max_body_size": "client_max_body_size",
                "proxy_max_temp_file_size": "proxy_max_temp_file_size",
                "access_list_id": "access_list_id",
                "auth_provider_id": "auth_provider_id",
                "auth_bypass_paths": "auth_bypass_paths",
                "ddns_enabled": "ddns_enabled",
                "ddns_provider_id": "ddns_provider_id",
                "ddns_proxied": "ddns_proxied",
                "forward_container_name": "forward_container_name",
                "forward_container_network": "forward_container_network",
            },
            id_fields={"access_list_id", "auth_provider_id", "ddns_provider_id"},
        )

        params = {"skip_nginx": "true"} if skip_nginx else None
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}", body, params=params)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_proxy_host_simple", description="CREATE a proxy host with common settings. REQUIRED: domain_names, forward_host, forward_port. Optional: forward_scheme (default 'http'), ssl_enabled, ssl_forced, enabled, block_exploits, waf_enabled, waf_use_global (all default true). For cache/streaming/DDNS use npg_create_proxy_host.")
async def npg_create_proxy_host_simple(
    domain_names: list[str],
    forward_host: str,
    forward_port: int,
    forward_scheme: str | None = None,
    ssl_enabled: bool = True,
    ssl_forced: bool = True,
    enabled: bool = True,
    block_exploits: bool = True,
    waf_enabled: bool = True,
    waf_use_global: bool = True,
) -> dict:
    try:
        _validate_required("domain_names", domain_names)
        _validate_required("forward_host", forward_host)
        _validate_required("forward_port", forward_port)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "domain_names": "domain_names",
                "forward_host": "forward_host",
                "forward_port": "forward_port",
                "forward_scheme": "forward_scheme",
                "ssl_enabled": "ssl_enabled",
                "ssl_forced": "ssl_force_https",
                "enabled": "enabled",
                "block_exploits": "block_exploits",
                "waf_enabled": "waf_enabled",
                "waf_use_global": "waf_use_global",
            },
        )

        data = c.post("/api/v1/proxy-hosts", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_simple", description="UPDATE a proxy host's common settings (partial update - omitted fields left as-is). REQUIRED: host_id. Optional: domain_names, forward_host, forward_port, forward_scheme, enabled, ssl_forced, ssl_cert_id. For advanced options use npg_update_proxy_host.")
async def npg_update_proxy_host_simple(
    host_id: str | int,
    domain_names: list[str] | None = None,
    forward_host: str | None = None,
    forward_port: int | None = None,
    forward_scheme: str | None = None,
    enabled: bool | None = None,
    ssl_forced: bool | None = None,
    ssl_cert_id: str | int | None = None,
) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "domain_names": "domain_names",
                "forward_host": "forward_host",
                "forward_port": "forward_port",
                "forward_scheme": "forward_scheme",
                "enabled": "enabled",
                "ssl_forced": "ssl_force_https",
                "ssl_cert_id": "certificate_id",
            },
            id_fields={"ssl_cert_id"},
        )

        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host", description="Delete a proxy host by its ID. REQUIRED: host_id.")
async def npg_delete_proxy_host(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}")
        return {"success": True, "message": f"Proxy host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_proxy_host", description="Test upstream connectivity for a proxy host. REQUIRED: host_id.")
async def npg_test_proxy_host(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/test")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_regenerate_config", description="Regenerate nginx config for a specific proxy host without touching others. REQUIRED: host_id.")
async def npg_regenerate_config(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/regenerate")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_sync_proxy_hosts", description="Sync all proxy host configs and reload nginx.")
async def npg_sync_proxy_hosts() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/proxy-hosts/sync")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_clone_proxy_host", description="Clone a proxy host with new domain names. Returns the new proxy host. REQUIRED: host_id, domain_names.")
async def npg_clone_proxy_host(host_id: str | int, domain_names: list[str]) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_required("domain_names", domain_names)
        c = _get_client()
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/clone", {"domain_names": domain_names})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_bulk_apply_certificate", description="Apply one certificate to multiple proxy hosts. REQUIRED: cert_id, host_ids (UUID list, max 50). Per-host results: success:true/result or success:false/error - one failure does not abort the batch. ssl_cert_id maps to API certificate_id. Over the 50-host cap raises ValueError; empty rejected.")
async def npg_bulk_apply_certificate(cert_id: str | int, host_ids: list[str | int]) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        _validate_required("host_ids", host_ids)
        if len(host_ids) > _BULK_HOST_LIMIT:
            raise ValueError(
                f"host_ids exceeds the limit of {_BULK_HOST_LIMIT} hosts per bulk call "
                f"(got {len(host_ids)})"
            )
        c = _get_client()
        results: list[dict] = []
        for host_id in host_ids:
            entry: dict = {"host_id": _id_path(host_id)}
            try:
                _validate_id("host_id", host_id)
                data = c.put(
                    f"/api/v1/proxy-hosts/{_id_path(host_id)}",
                    {"certificate_id": _id_path(cert_id)},
                )
                entry["success"] = True
                entry["result"] = data
            except Exception as e:
                entry["success"] = False
                entry["error"] = str(e)
            results.append(entry)
        return {"success": True, "data": results}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_bulk_delete_proxy_hosts", description="DESTRUCTIVE: DELETE multiple proxy hosts in one call. REQUIRED: host_ids (UUID list, max 50). Per-host result: deleted or success:false/error; one failure doesn't abort. Sub-configs (WAF, geo, fail2ban) cascade-delete. Over the 50-host cap raises ValueError; empty rejected.")
async def npg_bulk_delete_proxy_hosts(host_ids: list[str | int]) -> dict:
    try:
        _validate_required("host_ids", host_ids)
        if len(host_ids) > _BULK_HOST_LIMIT:
            raise ValueError(
                f"host_ids exceeds the limit of {_BULK_HOST_LIMIT} hosts per bulk call "
                f"(got {len(host_ids)})"
            )
        c = _get_client()
        results: list[dict] = []
        for host_id in host_ids:
            entry: dict = {"host_id": _id_path(host_id)}
            try:
                _validate_id("host_id", host_id)
                c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}")
                entry["success"] = True
                entry["result"] = {"deleted": True}
            except Exception as e:
                entry["success"] = False
                entry["error"] = str(e)
            results.append(entry)
        return {"success": True, "data": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Certificates ──────────────────────────────────────────────────────

@mcp.tool(name="npg_list_certificates", description="List all SSL/TLS certificates.")
async def npg_list_certificates() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/certificates")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_certificate", description="Get a certificate by its ID. REQUIRED: cert_id.")
async def npg_get_certificate(cert_id: str | int) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        c = _get_client()
        data = c.get(f"/api/v1/certificates/{_id_path(cert_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_certificate", description="Request a new Let's Encrypt certificate. Required: domain_names (array), email. Optional: provider (e.g. 'letsencrypt'), dns_provider_id, etc.")
async def npg_create_certificate(
    domain_names: list[str],
    email: str,
    provider: str = "letsencrypt",
    dns_provider_id: str | None = None,
) -> dict:
    try:
        _validate_required("domain_names", domain_names)
        _validate_required("email", email)
        c = _get_client()
        body = {
            "domain_names": domain_names,
            "email": email,
            "provider": provider,
            "dns_provider_id": dns_provider_id,
        }
        data = c.post("/api/v1/certificates", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_certificate", description="Delete a certificate by its ID. REQUIRED: cert_id.")
async def npg_delete_certificate(cert_id: str | int) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        c = _get_client()
        c.delete(f"/api/v1/certificates/{_id_path(cert_id)}")
        return {"success": True, "message": f"Certificate {_id_path(cert_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_renew_certificate", description="Renew a certificate by its ID. REQUIRED: cert_id.")
async def npg_renew_certificate(cert_id: str | int) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        c = _get_client()
        data = c.post(f"/api/v1/certificates/{_id_path(cert_id)}/renew")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_bulk_renew_certificates", description="RENEW multiple certificates in one call. REQUIRED: cert_ids (UUID list, max 20). Per-cert results: success:true or success:false/error - one failure does not abort the batch. Over the 20-cert cap raises ValueError before any renewal; empty rejected. Watch ACME/Let's Encrypt rate limits.")
async def npg_bulk_renew_certificates(cert_ids: list[str | int]) -> dict:
    try:
        _validate_required("cert_ids", cert_ids)
        if len(cert_ids) > _BULK_CERT_LIMIT:
            raise ValueError(
                f"cert_ids exceeds the limit of {_BULK_CERT_LIMIT} certificates per bulk call "
                f"(got {len(cert_ids)})"
            )
        c = _get_client()
        results: list[dict] = []
        for cert_id in cert_ids:
            entry: dict = {"cert_id": _id_path(cert_id)}
            try:
                _validate_id("cert_id", cert_id)
                data = c.post(f"/api/v1/certificates/{_id_path(cert_id)}/renew")
                entry["success"] = True
                entry["result"] = data
            except Exception as e:
                entry["success"] = False
                entry["error"] = str(e)
            results.append(entry)
        return {"success": True, "data": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Nginx ─────────────────────────────────────────────────────────────

@mcp.tool(name="npg_reload_nginx", description="Reload nginx configuration without full restart.")
async def npg_reload_nginx() -> dict:
    """Reload nginx configuration."""
    c = _get_client()
    try:
        c.post("/api/v1/proxy-hosts/sync")
        return {"success": True, "message": "Nginx reloaded"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_sync_nginx", description="Sync all configs and reload nginx.")
async def npg_sync_nginx() -> dict:
    """Sync all proxy hosts. Equivalent to nginx reload — tests config then reloads nginx."""
    c = _get_client()
    try:
        data = c.post("/api/v1/proxy-hosts/sync")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_nginx", description="TEST nginx configuration validity (runs `nginx -t` in the proxy container). Diagnostic only — does NOT regenerate host configs or reload nginx. Use npg_sync_nginx to apply changes. On invalid config returns success=false with the raw `nginx -t` error output.")
async def npg_test_nginx() -> dict:
    """Validate the running nginx configuration without reloading."""
    c = _get_client()
    try:
        data = c.post("/api/v1/test/nginx-config") or {}
        return {"success": True, "data": {"status": data.get("status", "ok"), "message": data.get("message")}}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Redirect Hosts ────────────────────────────────────────────────────

@mcp.tool(name="npg_list_redirect_hosts", description="List all redirect hosts.")
async def npg_list_redirect_hosts() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/redirect-hosts")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_redirect_host", description="Get a redirect host by its ID. REQUIRED: host_id.")
async def npg_get_redirect_host(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/redirect-hosts/{_id_path(host_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_redirect_host", description="Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, 301/302/307/308 only — 303 rejected by API v2.44.0+, default 301).")
async def npg_create_redirect_host(
    domain_names: list[str],
    forward_domain_name: str,
    forward_scheme: str = "auto",
    preserve_path: bool = True,
    redirect_code: Literal[301, 302, 307, 308] = 301,
) -> dict:
    try:
        _validate_required("domain_names", domain_names)
        _validate_required("forward_domain_name", forward_domain_name)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "domain_names": "domain_names",
                "forward_domain_name": "forward_domain_name",
                "forward_scheme": "forward_scheme",
                "preserve_path": "preserve_path",
                "redirect_code": "redirect_code",
            },
        )
        data = c.post("/api/v1/redirect-hosts", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_redirect_host", description="Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code (301/302/307/308 only — 303 rejected by API v2.44.0+). REQUIRED: host_id.")
async def npg_update_redirect_host(
    host_id: str | int,
    domain_names: list[str] | None = None,
    forward_domain_name: str | None = None,
    forward_scheme: str | None = None,
    preserve_path: bool | None = None,
    redirect_code: int | None = None,
) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "domain_names": "domain_names",
                "forward_domain_name": "forward_domain_name",
                "forward_scheme": "forward_scheme",
                "preserve_path": "preserve_path",
                "redirect_code": "redirect_code",
            },
        )
        data = c.put(f"/api/v1/redirect-hosts/{_id_path(host_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_redirect_host", description="Delete a redirect host by its ID. REQUIRED: host_id.")
async def npg_delete_redirect_host(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/redirect-hosts/{_id_path(host_id)}")
        return {"success": True, "message": f"Redirect host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Security Features (per proxy host) ────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_rate_limit", description="GET rate limit configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_rate_limit(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_rate_limit", description="UPDATE rate limit for a proxy host (partial update). REQUIRED: host_id. Optional: enabled, requests_per_second, burst_size, zone_size, limit_by (ip/uri/ip_uri), limit_response, disable_global (omit=inherit, false=inherit, true=disable), whitelist_ips (comma/newline IPs or CIDRs; omit=keep stored list, \"\"=clear; invalid entry 400).")
async def npg_update_proxy_host_rate_limit(host_id: str | int, enabled: bool | None = None, requests_per_second: int | None = None, burst_size: int | None = None, zone_size: str | None = None, limit_by: str | None = None, limit_response: int | None = None, disable_global: bool | None = None, whitelist_ips: str | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "requests_per_second": "requests_per_second",
                "burst_size": "burst_size",
                "zone_size": "zone_size",
                "limit_by": "limit_by",
                "limit_response": "limit_response",
                "disable_global": "disable_global",
                "whitelist_ips": "whitelist_ips",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_bot_filter", description="GET bot filter configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_bot_filter(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_bot_filter", description="UPDATE bot filter for a proxy host (partial update). REQUIRED: host_id. Optional: enabled, block_bad_bots, block_ai_bots, allow_search_engines, block_suspicious_clients, challenge_suspicious, custom_blocked/allowed_agents (csv), disable_global (omit=inherit, false=inherit, true=disable).")
async def npg_update_proxy_host_bot_filter(host_id: str | int, enabled: bool | None = None, block_bad_bots: bool | None = None, block_ai_bots: bool | None = None, allow_search_engines: bool | None = None, block_suspicious_clients: bool | None = None, challenge_suspicious: bool | None = None, disable_global: bool | None = None, custom_blocked_agents: str | None = None, custom_allowed_agents: str | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "block_bad_bots": "block_bad_bots",
                "block_ai_bots": "block_ai_bots",
                "allow_search_engines": "allow_search_engines",
                "block_suspicious_clients": "block_suspicious_clients",
                "challenge_suspicious": "challenge_suspicious",
                "disable_global": "disable_global",
                "custom_blocked_agents": "custom_blocked_agents",
                "custom_allowed_agents": "custom_allowed_agents",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_security_headers", description="GET security headers configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_security_headers(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_security_headers", description="UPDATE security headers for a proxy host (partial update). REQUIRED: host_id. Optional: enabled, hsts_*, x_frame_options (DENY/SAMEORIGIN), x_content_type_options, x_xss_protection, referrer_policy, content_security_policy, disable_global (omit=inherit, false=inherit, true=disable).")
async def npg_update_proxy_host_security_headers(host_id: str | int, enabled: bool | None = None, hsts_enabled: bool | None = None, hsts_max_age: int | None = None, hsts_include_subdomains: bool | None = None, hsts_preload: bool | None = None, x_frame_options: str | None = None, x_content_type_options: bool | None = None, x_xss_protection: bool | None = None, referrer_policy: str | None = None, content_security_policy: str | None = None, disable_global: bool | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "hsts_enabled": "hsts_enabled",
                "hsts_max_age": "hsts_max_age",
                "hsts_include_subdomains": "hsts_include_subdomains",
                "hsts_preload": "hsts_preload",
                "x_frame_options": "x_frame_options",
                "x_content_type_options": "x_content_type_options",
                "x_xss_protection": "x_xss_protection",
                "referrer_policy": "referrer_policy",
                "content_security_policy": "content_security_policy",
                "disable_global": "disable_global",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_apply_security_header_preset", description="APPLY a security header preset to a proxy host. preset: moderate, relaxed, or strict. REQUIRED: host_id.")
async def npg_apply_security_header_preset(host_id: str | int, preset: Literal["moderate", "relaxed", "strict"]) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_required("preset", preset)
        c = _get_client()
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers/preset/{preset}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_upstream", description="GET upstream/load balancing configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_upstream(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_upstream", description="UPDATE upstream/load-balancing for a proxy host. REQUIRED: host_id. Optional: scheme (http/https), servers (list of {address, port, weight, is_backup} - port separate field), load_balance (round_robin/least_conn/ip_hash/random), health_check_*.")
async def npg_update_proxy_host_upstream(host_id: str | int, scheme: str | None = None, servers: list[dict] | None = None, load_balance: str | None = None, health_check_enabled: bool | None = None, health_check_path: str | None = None, health_check_interval: int | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "scheme": "scheme",
                "servers": "servers",
                "load_balance": "load_balance",
                "health_check_enabled": "health_check_enabled",
                "health_check_path": "health_check_path",
                "health_check_interval": "health_check_interval",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_uri_block", description="GET URI block configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_uri_block(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_uri_block", description="UPDATE URI block configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips. REQUIRED: host_id.")
async def npg_update_proxy_host_uri_block(host_id: str | int, enabled: bool | None = None, rules: list[dict] | None = None, exception_ips: list[str] | None = None, allow_private_ips: bool | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "rules": "rules",
                "exception_ips": "exception_ips",
                "allow_private_ips": "allow_private_ips",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Settings ──────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_settings", description="Get global NPG settings.")
async def npg_get_settings() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_settings", description="Update global NPG settings. Pass only fields to change (dict).")
async def npg_update_settings(kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put("/api/v1/settings", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_system_settings", description="Get system settings (server name, timezone, locale).")
async def npg_get_system_settings() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-settings")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_system_settings", description="Update system settings. Pass only fields to change (dict).")
async def npg_update_system_settings(kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put("/api/v1/system-settings", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_dashboard", description="Get dashboard data (summary of proxy hosts, certificates, etc.).")
async def npg_get_dashboard() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dashboard")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_dashboard_health", description="Get system health status.")
async def npg_get_dashboard_health() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dashboard/health")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_dashboard_geoip_stats", description="GET GeoIP statistics by country for the dashboard.")
async def npg_get_dashboard_geoip_stats() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dashboard/geoip-stats")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Access Lists ──────────────────────────────────────────────────────

@mcp.tool(name="npg_list_access_lists", description="List all access lists (authentication/restriction lists).")
async def npg_list_access_lists() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/access-lists")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_access_list", description="Get an access list by its ID. REQUIRED: list_id.")
async def npg_get_access_list(list_id: str | int) -> dict:
    try:
        _validate_id("list_id", list_id)
        c = _get_client()
        data = c.get(f"/api/v1/access-lists/{_id_path(list_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_access_list", description="CREATE a new access list. REQUIRED: name. Optional: satisfy_any (bool, true=any rule matches, false=all must match), pass_auth (bool, allow authenticated users to bypass), description, items (list of dicts with directive=allow|deny, address=IP/CIDR/all, description, sort_order).")
async def npg_create_access_list(name: str, satisfy_any: bool | None = None, pass_auth: bool | None = None, description: str | None = None, items: list | None = None) -> dict:
    try:
        _validate_required("name", name)
        c = _get_client()
        # Non-standard: pre-seeded required field + optional if-not-None — kept as-is (not _build_body).
        body: dict = {"name": name}
        if satisfy_any is not None: body["satisfy_any"] = satisfy_any
        if pass_auth is not None: body["pass_auth"] = pass_auth
        if description is not None: body["description"] = description
        if items is not None: body["items"] = items
        data = c.post("/api/v1/access-lists", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_access_list", description="UPDATE an access list (partial update — omitted fields left as-is). REQUIRED: list_id. Optional: name, satisfy_any (bool), pass_auth (bool), description, items (list of dicts with directive=allow|deny, address=IP/CIDR/all).")
async def npg_update_access_list(list_id: str | int, name: str | None = None, satisfy_any: bool | None = None, pass_auth: bool | None = None, description: str | None = None, items: list | None = None) -> dict:
    try:
        _validate_id("list_id", list_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "name": "name",
                "satisfy_any": "satisfy_any",
                "pass_auth": "pass_auth",
                "description": "description",
                "items": "items",
            },
        )
        data = c.put(f"/api/v1/access-lists/{_id_path(list_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_access_list", description="Delete an access list by its ID. REQUIRED: list_id.")
async def npg_delete_access_list(list_id: str | int) -> dict:
    try:
        _validate_id("list_id", list_id)
        c = _get_client()
        c.delete(f"/api/v1/access-lists/{_id_path(list_id)}")
        return {"success": True, "message": f"Access list {_id_path(list_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── DNS Providers ─────────────────────────────────────────────────────

@mcp.tool(name="npg_list_dns_providers", description="List all DNS providers configured for DNS-01 challenges.")
async def npg_list_dns_providers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dns-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_dns_provider", description="Get a DNS provider by its ID. REQUIRED: provider_id.")
async def npg_get_dns_provider(provider_id: str | int) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        data = c.get(f"/api/v1/dns-providers/{_id_path(provider_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_dns_provider", description="Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}).")
async def npg_create_dns_provider(name: str, provider_type: str, credentials: dict | None = None, kwargs: dict | None = None) -> dict:
    try:
        _validate_required("name", name)
        _validate_required("provider_type", provider_type)
        c = _get_client()
        body: dict[str, Any] = {"name": name, "provider_type": provider_type}
        if credentials:
            body["credentials"] = credentials
        if kwargs:
            body.update(kwargs)
        data = c.post("/api/v1/dns-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_dns_provider", description="Update a DNS provider. Pass only fields to change (dict). REQUIRED: provider_id.")
async def npg_update_dns_provider(provider_id: str | int, kwargs: dict | None = None) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        data = c.put(f"/api/v1/dns-providers/{_id_path(provider_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_dns_provider", description="Delete a DNS provider by its ID. REQUIRED: provider_id.")
async def npg_delete_dns_provider(provider_id: str | int) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        c.delete(f"/api/v1/dns-providers/{_id_path(provider_id)}")
        return {"success": True, "message": f"DNS provider {_id_path(provider_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_dns_provider", description="Test DNS provider credentials. REQUIRED: provider_id.")
async def npg_test_dns_provider(provider_id: str | int) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        data = c.post("/api/v1/dns-providers/test", {"dns_provider_id": provider_id})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Cloud Providers ───────────────────────────────────────────────────

@mcp.tool(name="npg_list_cloud_providers", description="List all cloud providers (for certificate DNS challenges).")
async def npg_list_cloud_providers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/cloud-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_cloud_provider", description="Get a cloud provider by its slug.")
async def npg_get_cloud_provider(slug: str) -> dict:
    try:
        _validate_id("slug", slug)
        c = _get_client()
        data = c.get(f"/api/v1/cloud-providers/{slug}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_cloud_provider", description="Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description.")
async def npg_create_cloud_provider(name: str, slug: str, ip_ranges: list[str], region: str | None = None, description: str | None = None, kwargs: dict | None = None) -> dict:
    try:
        _validate_required("name", name)
        _validate_id("slug", slug)
        _validate_required("ip_ranges", ip_ranges)
        c = _get_client()
        body = {"name": name, "slug": slug, "ip_ranges": ip_ranges}
        if region:
            body["region"] = region
        if description:
            body["description"] = description
        if kwargs:
            body.update(kwargs)
        data = c.post("/api/v1/cloud-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_cloud_provider", description="Update a cloud provider by its slug. Pass only fields to change (dict).")
async def npg_update_cloud_provider(slug: str, kwargs: dict | None = None) -> dict:
    try:
        _validate_id("slug", slug)
        c = _get_client()
        data = c.put(f"/api/v1/cloud-providers/{slug}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_cloud_provider", description="Delete a cloud provider by its slug.")
async def npg_delete_cloud_provider(slug: str) -> dict:
    try:
        _validate_id("slug", slug)
        c = _get_client()
        c.delete(f"/api/v1/cloud-providers/{slug}")
        return {"success": True, "message": f"Cloud provider {slug} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_cloud_blocking", description="GET per-host cloud provider blocking configuration. Returns blocked_providers, challenge_mode, allow_search_bots, cloud_disable_global. REQUIRED: host_id.")
async def npg_get_proxy_host_cloud_blocking(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/blocked-cloud-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_cloud_blocking", description="UPDATE per-host cloud blocking (endpoint full-replaces; tool merges current + provided, so omitted fields left as-is). REQUIRED: host_id. Optional: blocked_providers (slugs), challenge_mode, allow_search_bots, cloud_disable_global (omit=inherit, false=inherit, true=disable).")
async def npg_update_proxy_host_cloud_blocking(host_id: str | int, blocked_providers: list[str] | None = None, challenge_mode: bool | None = None, allow_search_bots: bool | None = None, cloud_disable_global: bool | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        # Read-modify-write: upstream SetBlockedProviders full-replaces all 4 fields.
        current = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/blocked-cloud-providers") or {}
        body = {
            "blocked_providers": blocked_providers if blocked_providers is not None else (current.get("blocked_providers") or []),
            "challenge_mode": challenge_mode if challenge_mode is not None else bool(current.get("challenge_mode", False)),
            "allow_search_bots": allow_search_bots if allow_search_bots is not None else bool(current.get("allow_search_bots", False)),
            "cloud_disable_global": cloud_disable_global if cloud_disable_global is not None else bool(current.get("cloud_disable_global", False)),
        }
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/blocked-cloud-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── GeoIP ─────────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_geoip_status", description="Get GeoIP database update status.")
async def npg_get_geoip_status() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-settings/geoip/status")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_geoip", description="Update GeoIP databases.")
async def npg_update_geoip() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/system-settings/geoip/update")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_list_countries", description="List available country codes for GeoIP blocking.")
async def npg_list_countries() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/geo/countries")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_geo", description="GET geo restriction configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_geo(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_proxy_host_geo", description="CREATE geo restriction for a proxy host. Required: host_id, countries (list of ISO codes, min 1). Optional: mode (whitelist/blacklist, default blacklist), allowed_ips, challenge_mode, disable_global (bool — false=inherit, true=disable global), allow_private_ips, allow_search_bots")
async def npg_create_proxy_host_geo(host_id: str | int, countries: list[str], mode: Literal["whitelist", "blacklist"] = "blacklist", enabled: bool = True, allowed_ips: list[str] | None = None, challenge_mode: bool = False, disable_global: bool = False, allow_private_ips: bool = True, allow_search_bots: bool = True) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_required("countries", countries)
        c = _get_client()
        # Non-standard: pre-seeded defaults dict (create semantics) + conditional — kept as-is (not _build_body).
        body: dict = {"mode": mode, "countries": countries, "enabled": enabled, "challenge_mode": challenge_mode, "disable_global": disable_global, "allow_private_ips": allow_private_ips, "allow_search_bots": allow_search_bots}
        if allowed_ips is not None: body["allowed_ips"] = allowed_ips
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_geo", description="UPDATE geo restriction for a proxy host (partial update). REQUIRED: host_id. Optional: enabled, mode (whitelist/blacklist), countries (ISO codes), allowed_ips, challenge_mode, allow_private_ips, allow_search_bots, disable_global (omit=inherit, false=inherit, true=disable).")
async def npg_update_proxy_host_geo(host_id: str | int, enabled: bool | None = None, mode: Literal["whitelist", "blacklist"] | None = None, countries: list[str] | None = None, allowed_ips: list[str] | None = None, challenge_mode: bool | None = None, disable_global: bool | None = None, allow_private_ips: bool | None = None, allow_search_bots: bool | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "mode": "mode",
                "countries": "countries",
                "allowed_ips": "allowed_ips",
                "challenge_mode": "challenge_mode",
                "disable_global": "disable_global",
                "allow_private_ips": "allow_private_ips",
                "allow_search_bots": "allow_search_bots",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_geo", description="DELETE geo restriction for a proxy host. REQUIRED: host_id.")
async def npg_delete_proxy_host_geo(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo")
        return {"success": True, "message": f"Geo restriction for host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Fail2ban (per proxy host) ─────────────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_fail2ban", description="GET fail2ban configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_fail2ban(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_fail2ban", description="UPDATE fail2ban configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, max_retries, find_time (seconds), ban_time (seconds, 0=permanent), fail_codes, action (block/challenge). REQUIRED: host_id.")
async def npg_update_proxy_host_fail2ban(host_id: str | int, enabled: bool | None = None, max_retries: int | None = None, find_time: int | None = None, ban_time: int | None = None, fail_codes: str | None = None, action: Literal["block", "challenge"] | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "max_retries": "max_retries",
                "find_time": "find_time",
                "ban_time": "ban_time",
                "fail_codes": "fail_codes",
                "action": "action",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Challenge/CAPTCHA (per proxy host) ────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_challenge", description="GET CAPTCHA/challenge configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_challenge(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_challenge", description="UPDATE CAPTCHA/challenge configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), challenge_type (str), site_key (str), token_validity (int), min_score (float), apply_to (str), page_title (str) REQUIRED: host_id.")
async def npg_update_proxy_host_challenge(host_id: str | int, enabled: bool | None = None, challenge_type: str | None = None, site_key: str | None = None, token_validity: int | None = None, min_score: float | None = None, apply_to: str | None = None, page_title: str | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "challenge_type": "challenge_type",
                "site_key": "site_key",
                "token_validity": "token_validity",
                "min_score": "min_score",
                "apply_to": "apply_to",
                "page_title": "page_title",
            },
        )
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_challenge", description="DELETE CAPTCHA/challenge configuration for a proxy host. REQUIRED: host_id.")
async def npg_delete_proxy_host_challenge(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge")
        return {"success": True, "message": f"Challenge configuration for host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_verify_challenge", description="Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution.")
async def npg_verify_challenge(token: str, solution: str) -> dict:
    try:
        _validate_required("token", token)
        _validate_required("solution", solution)
        c = _get_client()
        data = c.post("/api/v1/challenge/verify", {"token": token, "solution": solution})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Security (banned IPs, etc.) ───────────────────────────────────────

@mcp.tool(name="npg_list_banned_ips", description="List banned IP addresses.")
async def npg_list_banned_ips() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/banned-ips")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_ban_ip", description="Ban an IP address. REQUIRED: ip_address. Optional: reason, ban_time (seconds, 0=permanent — default 3600). After banning, verify with npg_list_banned_ips; release with npg_unban_ip (by ID) or npg_unban_ip_by_address.")
async def npg_ban_ip(ip_address: str, reason: str = "Manual ban via API", ban_time: int = 3600) -> dict:
    """Ban an IP address. Required: ip_address. Optional: reason, ban_time (seconds, 0=permanent)."""
    try:
        _validate_required("ip_address", ip_address)
        c = _get_client()
        data = c.post("/api/v1/banned-ips", {"ip_address": ip_address, "reason": reason, "ban_time": ban_time})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_unban_ip", description="Unban an IP by its ID. REQUIRED: ip_id.")
async def npg_unban_ip(ip_id: str | int) -> dict:
    try:
        _validate_id("ip_id", ip_id)
        c = _get_client()
        c.delete(f"/api/v1/banned-ips/{_id_path(ip_id)}")
        return {"success": True, "message": f"IP ban {_id_path(ip_id)} removed"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_unban_ip_by_address", description="Unban an IP address without needing its ban record ID. REQUIRED: ip (the IP address string, e.g. '1.2.3.4').")
async def npg_unban_ip_by_address(ip: str) -> dict:
    try:
        _validate_required("ip", ip)
        c = _get_client()
        c.delete("/api/v1/banned-ips", params={"ip": ip})
        return {"success": True, "message": f"IP {ip} unbanned"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_ban_duration", description="RE-DATE an existing ban: change how long it still runs. REQUIRED: ban_id (UUID), ban_time (seconds from NOW — counts from now, not from when the ban started; 0 = permanent ban). Does not regenerate nginx configs. Verify with npg_list_banned_ips.")
async def npg_update_ban_duration(ban_id: str | int, ban_time: int) -> dict:
    """Re-date an existing ban. ban_time is seconds from now; 0 makes it permanent."""
    try:
        _validate_id("ban_id", ban_id)
        c = _get_client()
        data = c.put(f"/api/v1/banned-ips/{_id_path(ban_id)}/duration", {"ban_time": ban_time})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_bots_known", description="Get list of known bot user-agent signatures.")
async def npg_get_bots_known() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/bots/known")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_security_headers_presets", description="Get available security header presets.")
async def npg_get_security_headers_presets() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/security-headers/presets")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Exploit Rules ─────────────────────────────────────────────────────

@mcp.tool(name="npg_list_exploit_rules", description="List exploit block rules.")
async def npg_list_exploit_rules() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/exploit-rules")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_exploit_rule", description="Get an exploit rule by its ID. REQUIRED: rule_id.")
async def npg_get_exploit_rule(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.get(f"/api/v1/exploit-rules/{_id_path(rule_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_exploit_rule", description="Create an exploit block rule. Required: category, name, pattern, pattern_type (e.g. 'query_string'). Optional: severity, description.")
async def npg_create_exploit_rule(category: str, name: str, pattern: str, pattern_type: str, severity: str | None = None, description: str | None = None, kwargs: dict | None = None) -> dict:
    try:
        _validate_required("category", category)
        _validate_required("name", name)
        _validate_required("pattern", pattern)
        _validate_required("pattern_type", pattern_type)
        c = _get_client()
        body = {"category": category, "name": name, "pattern": pattern, "pattern_type": pattern_type}
        if severity:
            body["severity"] = severity
        if description:
            body["description"] = description
        if kwargs:
            body.update(kwargs)
        data = c.post("/api/v1/exploit-rules", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_exploit_rule", description="Update an exploit rule. Pass only fields to change (dict). REQUIRED: rule_id.")
async def npg_update_exploit_rule(rule_id: str | int, kwargs: dict | None = None) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.put(f"/api/v1/exploit-rules/{_id_path(rule_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_exploit_rule", description="Delete an exploit rule by its ID. REQUIRED: rule_id.")
async def npg_delete_exploit_rule(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        c.delete(f"/api/v1/exploit-rules/{_id_path(rule_id)}")
        return {"success": True, "message": f"Exploit rule {_id_path(rule_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_toggle_exploit_rule", description="Toggle an exploit rule's enabled status. REQUIRED: rule_id.")
async def npg_toggle_exploit_rule(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.post(f"/api/v1/exploit-rules/{_id_path(rule_id)}/toggle")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── WAF ───────────────────────────────────────────────────────────────

@mcp.tool(name="npg_list_waf_rules", description="List all WAF (Web Application Firewall) rules.")
async def npg_list_waf_rules() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/waf/rules")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_waf_hosts", description="Get WAF config for all proxy hosts.")
async def npg_get_waf_hosts() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/waf/hosts")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_waf_host_config", description="Get WAF config for a specific proxy host. REQUIRED: host_id.")
async def npg_get_waf_host_config(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/waf/hosts/{_id_path(host_id)}/config")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_disable_waf_rule", description="Disable a WAF rule for a specific proxy host. REQUIRED: host_id, rule_id.")
async def npg_disable_waf_rule(host_id: str | int, rule_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.post(f"/api/v1/waf/hosts/{_id_path(host_id)}/rules/{_id_path(rule_id)}/disable")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Logs ──────────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_logs", description="GET access logs. Optional filters: host, status (HTTP status code), method (e.g. GET/POST), limit (page size, the API maps it to per_page), offset (row offset, converted to page). REQUIRED: none — zero-arg call returns the full default log set.")
async def npg_get_logs(
    host: str | None = None,
    status: int | None = None,
    method: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    c = _get_client()
    try:
        params = _list_params_per_page(limit=limit, offset=offset)
        if host is not None and str(host).strip():
            params["host"] = str(host)
        if status is not None:
            _validate_query_int("status", status)
            params["status"] = status
        if method is not None and str(method).strip():
            params["method"] = str(method)
        data = c.get("/api/v1/logs", params=params or None)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_settings", description="Get log settings.")
async def npg_get_log_settings() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/settings")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_log_settings", description="Update log settings. Pass only fields to change (dict).")
async def npg_update_log_settings(kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put("/api/v1/logs/settings", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_stats", description="Get log statistics.")
async def npg_get_log_stats() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/stats")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_list_audit_logs", description="LIST audit log entries. Optional filters: page, limit, action, resource_type. REQUIRED: none — zero-arg call returns the full audit log set.")
async def npg_list_audit_logs(
    page: int | None = None,
    limit: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
) -> dict:
    c = _get_client()
    try:
        params = _list_params(limit=limit, page=page)
        if action is not None and str(action).strip():
            params["action"] = str(action)
        if resource_type is not None and str(resource_type).strip():
            params["resource_type"] = str(resource_type)
        data = c.get("/api/v1/audit-logs", params=params or None)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_list_system_logs", description="LIST system logs. Optional filters: source, level, limit. REQUIRED: none — zero-arg call returns the full system log set.")
async def npg_list_system_logs(
    source: str | None = None,
    level: str | None = None,
    limit: int | None = None,
) -> dict:
    c = _get_client()
    try:
        params = _list_params(limit=limit)
        if source is not None and str(source).strip():
            params["source"] = str(source)
        if level is not None and str(level).strip():
            params["level"] = str(level)
        data = c.get("/api/v1/system-logs", params=params or None)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Backups ───────────────────────────────────────────────────────────

@mcp.tool(name="npg_list_backups", description="List all backups.")
async def npg_list_backups() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/backups")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_backup", description="Get a backup by its ID. REQUIRED: backup_id.")
async def npg_get_backup(backup_id: str | int) -> dict:
    try:
        _validate_id("backup_id", backup_id)
        c = _get_client()
        data = c.get(f"/api/v1/backups/{_id_path(backup_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_backup", description="Create a new backup.")
async def npg_create_backup() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/backups")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_backup", description="Delete a backup by its ID. REQUIRED: backup_id.")
async def npg_delete_backup(backup_id: str | int) -> dict:
    try:
        _validate_id("backup_id", backup_id)
        c = _get_client()
        c.delete(f"/api/v1/backups/{_id_path(backup_id)}")
        return {"success": True, "message": f"Backup {_id_path(backup_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_restore_backup", description="Restore from a backup. Required: backup_id.")
async def npg_restore_backup(backup_id: str | int) -> dict:
    try:
        _validate_id("backup_id", backup_id)
        c = _get_client()
        data = c.post(f"/api/v1/backups/{_id_path(backup_id)}/restore")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── API Tokens ────────────────────────────────────────────────────────

@mcp.tool(name="npg_list_api_tokens", description="List all API tokens.")
async def npg_list_api_tokens() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/api-tokens")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_api_token", description="Get an API token by its ID. REQUIRED: token_id.")
async def npg_get_api_token(token_id: str | int) -> dict:
    try:
        _validate_id("token_id", token_id)
        c = _get_client()
        data = c.get(f"/api/v1/api-tokens/{_id_path(token_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_api_token", description="Create a new API token. Required: name, permissions (array). Optional: expires_at.")
async def npg_create_api_token(name: str, permissions: list[str], expires_at: str | None = None) -> dict:
    try:
        _validate_required("name", name)
        _validate_required("permissions", permissions)
        c = _get_client()
        body = {"name": name, "permissions": permissions, "expires_at": expires_at}
        data = c.post("/api/v1/api-tokens", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_api_token", description="Update an API token. Pass only fields to change (dict). REQUIRED: token_id.")
async def npg_update_api_token(token_id: str | int, kwargs: dict | None = None) -> dict:
    try:
        _validate_id("token_id", token_id)
        c = _get_client()
        data = c.put(f"/api/v1/api-tokens/{_id_path(token_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_revoke_api_token", description="Revoke an API token by its ID. REQUIRED: token_id.")
async def npg_revoke_api_token(token_id: str | int) -> dict:
    try:
        _validate_id("token_id", token_id)
        c = _get_client()
        data = c.post(f"/api/v1/api-tokens/{_id_path(token_id)}/revoke")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_api_token", description="Delete an API token by its ID. REQUIRED: token_id.")
async def npg_delete_api_token(token_id: str | int) -> dict:
    try:
        _validate_id("token_id", token_id)
        c = _get_client()
        c.delete(f"/api/v1/api-tokens/{_id_path(token_id)}")
        return {"success": True, "message": f"API token {_id_path(token_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Notification Channels ──────────────────────────────────────────────

@mcp.tool(name="npg_list_notification_channels", description="List all notification channels.")
async def npg_list_notification_channels() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/notification-channels")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_notification_channel", description="CREATE a notification channel. REQUIRED: name, channel_type (webhook/discord/telegram). Optional: config (dict: url for webhook/discord; bot_token+chat_id for telegram), events (at least one event or digest_enabled), allow_private_target, digest_enabled, digest_hour (0-23).")
async def npg_create_notification_channel(name: str, channel_type: str, config: dict | None = None, events: list[str] | None = None, allow_private_target: bool = False, digest_enabled: bool = False, digest_hour: int = 9) -> dict:
    try:
        _validate_required("name", name)
        _validate_required("channel_type", channel_type)
        c = _get_client()
        body = {"name": name, "type": channel_type, "allow_private_target": allow_private_target, "digest_enabled": digest_enabled, "digest_hour": digest_hour}
        if config:
            body["config"] = config
        if events:
            body["events"] = events
        data = c.post("/api/v1/notification-channels", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_notification_channel", description="UPDATE a notification channel (read-modify-write; current channel fetched and merged before PUT). REQUIRED: channel_id. Optional: name, channel_type, config (url/bot_token/chat_id), events, enabled, digest_enabled, digest_hour, allow_private_target, rich_format, language, dashboard_url, template.")
async def npg_update_notification_channel(channel_id: str | int, name: str | None = None, channel_type: str | None = None, config: dict | None = None, events: list[str] | None = None, enabled: bool | None = None, digest_enabled: bool | None = None, digest_hour: int | None = None, allow_private_target: bool | None = None, rich_format: bool | None = None, language: str | None = None, dashboard_url: str | None = None, template: str | None = None) -> dict:
    try:
        _validate_id("channel_id", channel_id)
        c = _get_client()
        cid = _id_path(channel_id)
        # Read-modify-write: API is full-replace (UpdateNotificationChannelRequest = CreateNotificationChannelRequest)
        # There is no GET /:id endpoint, so we use the list endpoint and find by ID
        listing = c.get("/api/v1/notification-channels")
        existing: dict = {}
        if listing and isinstance(listing, dict):
            for ch in listing.get("data", []):
                if ch.get("id") == cid:
                    existing = ch
                    break
        body: dict = {
            "name": existing.get("name", ""),
            "type": existing.get("type", "webhook"),
            "config": existing.get("config", {}),
            "events": existing.get("events", []),
            "digest_events": existing.get("digest_events", []),
            "rich_format": existing.get("rich_format", False),
            "language": existing.get("language", "en"),
            "dashboard_url": existing.get("dashboard_url", ""),
            "digest_enabled": existing.get("digest_enabled", False),
            "digest_hour": existing.get("digest_hour", 9),
            "allow_private_target": existing.get("allow_private_target", False),
            "template": existing.get("template", ""),
        }
        if enabled is not None: body["enabled"] = enabled
        # Overlay provided fields (read-modify-write pattern — kept as-is, not _build_body)
        if name is not None: body["name"] = name
        if channel_type is not None: body["type"] = channel_type
        if config is not None: body["config"] = config
        if events is not None: body["events"] = events
        if digest_enabled is not None: body["digest_enabled"] = digest_enabled
        if digest_hour is not None: body["digest_hour"] = digest_hour
        if allow_private_target is not None: body["allow_private_target"] = allow_private_target
        if rich_format is not None: body["rich_format"] = rich_format
        if language is not None: body["language"] = language
        if dashboard_url is not None: body["dashboard_url"] = dashboard_url
        if template is not None: body["template"] = template
        data = c.put(f"/api/v1/notification-channels/{cid}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_notification_channel", description="Delete a notification channel by its ID. REQUIRED: channel_id.")
async def npg_delete_notification_channel(channel_id: str | int) -> dict:
    try:
        _validate_id("channel_id", channel_id)
        c = _get_client()
        c.delete(f"/api/v1/notification-channels/{_id_path(channel_id)}")
        return {"success": True, "message": f"Notification channel {_id_path(channel_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_notification_channel", description="Test a notification channel by sending a test message. REQUIRED: channel_id.")
async def npg_test_notification_channel(channel_id: str | int) -> dict:
    try:
        _validate_id("channel_id", channel_id)
        c = _get_client()
        data = c.post(f"/api/v1/notification-channels/{_id_path(channel_id)}/test")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_notification_deliveries", description="Get delivery history for a notification channel. REQUIRED: channel_id.")
async def npg_get_notification_deliveries(channel_id: str | int) -> dict:
    try:
        _validate_id("channel_id", channel_id)
        c = _get_client()
        data = c.get(f"/api/v1/notification-channels/{_id_path(channel_id)}/deliveries")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_detect_telegram_chats", description="DETECT available Telegram chats for notification delivery. REQUIRED: bot_token (Telegram bot API token). Optional: channel_id (existing channel ID to look up stored token). Sends bot_token in the request body; Telegram must be reachable from the NPG server.")
async def npg_detect_telegram_chats(bot_token: str | None = None, channel_id: str | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {"bot_token": "bot_token", "channel_id": "channel_id"},
        )
        data = c.post("/api/v1/notification-channels/detect-telegram-chats", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Users ──────────────────────────────────────────────────────────────

@mcp.tool(name="npg_list_users", description="List all users.")
async def npg_list_users() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/users")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_user", description="Get a user by their ID. REQUIRED: user_id.")
async def npg_get_user(user_id: str | int) -> dict:
    try:
        _validate_id("user_id", user_id)
        c = _get_client()
        data = c.get(f"/api/v1/users/{_id_path(user_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_user", description="CREATE a new user. REQUIRED: username, email, password, role_id (UUID of a valid role — use npg_list_roles to find one). Optional: is_active. The API rejects creation without a valid role_id (empty string causes 500).")
async def npg_create_user(username: str, email: str, password: str, role_id: str | int, is_active: bool = True) -> dict:
    try:
        _validate_required("username", username)
        _validate_required("email", email)
        _validate_required("password", password)
        _validate_id("role_id", role_id)
        c = _get_client()
        body = {"username": username, "email": email, "password": password, "role_id": _id_path(role_id), "is_active": is_active}
        data = c.post("/api/v1/users", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_set_user_password", description="Set/reset a user's password. Required: user_id, new_password.")
async def npg_set_user_password(user_id: str | int, new_password: str) -> dict:
    try:
        _validate_id("user_id", user_id)
        _validate_required("new_password", new_password)
        c = _get_client()
        data = c.put(f"/api/v1/users/{_id_path(user_id)}/password", {"password": new_password})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_end_user_sessions", description="End all sessions for a user (force logout). Required: user_id.")
async def npg_end_user_sessions(user_id: str | int) -> dict:
    try:
        _validate_id("user_id", user_id)
        c = _get_client()
        data = c.post(f"/api/v1/users/{_id_path(user_id)}/end-sessions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_user", description="Delete a user by their ID. REQUIRED: user_id.")
async def npg_delete_user(user_id: str | int) -> dict:
    try:
        _validate_id("user_id", user_id)
        c = _get_client()
        c.delete(f"/api/v1/users/{_id_path(user_id)}")
        return {"success": True, "message": f"User {_id_path(user_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Roles ──────────────────────────────────────────────────────────────

@mcp.tool(name="npg_list_roles", description="List all roles.")
async def npg_list_roles() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/roles")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_role", description="CREATE a new role. REQUIRED: name. Optional: description, permissions (array of 'area:verb' strings, e.g. ['proxy:read','proxy:write']). Use npg_get_permission_areas to list valid areas and verbs.")
async def npg_create_role(name: str, permissions: list[str] | None = None, description: str = "") -> dict:
    try:
        _validate_required("name", name)
        c = _get_client()
        body = {"name": name, "description": description, "permissions": permissions or []}
        data = c.post("/api/v1/roles", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_role", description="UPDATE a role (partial update — omitted fields left as-is). REQUIRED: role_id. Optional: name, description, permissions (array of 'area:verb' strings).")
async def npg_update_role(role_id: str | int, name: str | None = None, description: str | None = None, permissions: list[str] | None = None) -> dict:
    try:
        _validate_id("role_id", role_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {"name": "name", "description": "description", "permissions": "permissions"},
        )
        data = c.put(f"/api/v1/roles/{_id_path(role_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_role", description="Delete a role by its ID. REQUIRED: role_id.")
async def npg_delete_role(role_id: str | int) -> dict:
    try:
        _validate_id("role_id", role_id)
        c = _get_client()
        c.delete(f"/api/v1/roles/{_id_path(role_id)}")
        return {"success": True, "message": f"Role {_id_path(role_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── SSO Providers ──────────────────────────────────────────────────────

@mcp.tool(name="npg_list_sso_providers", description="List all SSO providers.")
async def npg_list_sso_providers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/sso-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_sso_provider", description="CREATE an SSO (OIDC) provider. REQUIRED: slug, name, issuer_url, client_id. Optional: client_secret (placeholder), scopes, trust_provider_email (only if you control the provider), allowed_email_domains, allowed_emails, group_claim, required_group, default_role_id. Verify via npg_list_sso_providers.")
async def npg_create_sso_provider(slug: str, name: str, issuer_url: str, client_id: str, client_secret: str | None = None, scopes: str | None = None, trust_provider_email: bool = False) -> dict:
    try:
        _validate_id("slug", slug)
        _validate_required("name", name)
        _validate_required("issuer_url", issuer_url)
        _validate_id("client_id", client_id)
        c = _get_client()
        body = {"slug": slug, "name": name, "issuer_url": issuer_url, "client_id": client_id, "trust_provider_email": trust_provider_email}
        if client_secret is not None:
            body["client_secret"] = client_secret
        if scopes is not None:
            body["scopes"] = scopes
        data = c.post("/api/v1/sso-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_sso_provider", description="UPDATE an SSO provider (read-modify-write; full-replace API merged before PUT). REQUIRED: provider_id. Optional: name, slug, issuer_url, client_id, client_secret (masked), scopes, trust_provider_email, allowed_email_domains, allowed_emails, group_claim, required_group, default_role_id.")
async def npg_update_sso_provider(provider_id: str | int, name: str | None = None, slug: str | None = None, issuer_url: str | None = None, client_id: str | None = None, client_secret: str | None = None, scopes: str | None = None, callback_base_url: str | None = None, enabled: bool | None = None, allow_jit: bool | None = None, trust_provider_email: bool | None = None, allowed_email_domains: list[str] | None = None, allowed_emails: list[str] | None = None, group_claim: str | None = None, required_group: str | None = None, default_role_id: str | None = None) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        cid = _id_path(provider_id)
        # Read-modify-write: API PUT is full-replace (requires slug, issuer_url, client_id, client_secret)
        # No GET /sso-providers/{id} exists, so fetch the list and find by ID
        providers = c.get("/api/v1/sso-providers")
        current = None
        if isinstance(providers, dict):
            items = providers.get("data", [])
        elif isinstance(providers, list):
            items = providers
        else:
            items = []
        for p in items:
            if p.get("id") == cid:
                current = p
                break
        if current is None:
            return {"success": False, "error": f"SSO provider {cid} not found"}
        # Read-modify-write full-replace merge — kept as-is (not _build_body).
        # Start with current values for full-replace fields
        body: dict = {"slug": current.get("slug", ""), "issuer_url": current.get("issuer_url", ""), "client_id": current.get("client_id", ""), "client_secret": current.get("client_secret", "********")}
        # Merge all current non-replace fields (incl. trust_provider_email to avoid data-loss)
        for k in ("name", "scopes", "callback_base_url", "enabled", "allow_jit", "trust_provider_email", "allowed_email_domains", "allowed_emails", "group_claim", "required_group", "default_role_id"):
            if current.get(k) is not None:
                body[k] = current[k]
        # Override with provided values
        if name is not None: body["name"] = name
        if slug is not None: body["slug"] = slug
        if issuer_url is not None: body["issuer_url"] = issuer_url
        if client_id is not None: body["client_id"] = client_id
        if client_secret is not None: body["client_secret"] = client_secret
        if scopes is not None: body["scopes"] = scopes
        if callback_base_url is not None: body["callback_base_url"] = callback_base_url
        if enabled is not None: body["enabled"] = enabled
        if allow_jit is not None: body["allow_jit"] = allow_jit
        if trust_provider_email is not None: body["trust_provider_email"] = trust_provider_email
        if allowed_email_domains is not None: body["allowed_email_domains"] = allowed_email_domains
        if allowed_emails is not None: body["allowed_emails"] = allowed_emails
        if group_claim is not None: body["group_claim"] = group_claim
        if required_group is not None: body["required_group"] = required_group
        if default_role_id is not None: body["default_role_id"] = default_role_id
        data = c.put(f"/api/v1/sso-providers/{cid}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_sso_provider", description="Delete an SSO provider by its ID. REQUIRED: provider_id.")
async def npg_delete_sso_provider(provider_id: str | int) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        c.delete(f"/api/v1/sso-providers/{_id_path(provider_id)}")
        return {"success": True, "message": f"SSO provider {_id_path(provider_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_sso_provider", description="Probe an OIDC issuer's discovery document without creating a provider. REQUIRED: issuer_url. Optional: scopes (space-separated, must contain 'openid', default 'openid profile email'). Returns endpoints, scopes_supported, supports_pkce, missing_scopes.")
async def npg_test_sso_provider(issuer_url: str, scopes: str | None = None) -> dict:
    try:
        _validate_required("issuer_url", issuer_url)
        c = _get_client()
        body: dict = {"issuer_url": issuer_url}
        if scopes is not None:
            body["scopes"] = scopes
        data = c.post("/api/v1/sso-providers/test", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Log Files ──────────────────────────────────────────────────────────

@mcp.tool(name="npg_list_log_files", description="List all log files.")
async def npg_list_log_files() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-settings/log-files")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_download_log_file", description="Download a log file by its filename. Returns the raw log content.")
async def npg_download_log_file(filename: str) -> dict:
    try:
        _validate_required("filename", filename)
        c = _get_client()
        encoded = quote(filename, safe="")
        data = c.get_text(f"/api/v1/system-settings/log-files/{encoded}/download")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_view_log_file", description="View the contents of a log file. REQUIRED: filename.")
async def npg_view_log_file(filename: str, lines: int = 100) -> dict:
    try:
        _validate_required("filename", filename)
        c = _get_client()
        encoded = quote(filename, safe="")
        data = c.get(f"/api/v1/system-settings/log-files/{encoded}/view", params={"lines": lines})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_rotate_log_file", description="Rotate a log file by its filename.")
async def npg_rotate_log_file() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/system-settings/log-files/rotate")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_log_file", description="Delete a log file by its filename.")
async def npg_delete_log_file(filename: str) -> dict:
    try:
        _validate_required("filename", filename)
        c = _get_client()
        encoded = quote(filename, safe="")
        c.delete(f"/api/v1/system-settings/log-files/{encoded}")
        return {"success": True, "message": f"Log file {filename} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Certificates ───────────────────────────────────────────────────────

@mcp.tool(name="npg_get_expiring_certificates", description="Get certificates that are expiring soon.")
async def npg_get_expiring_certificates() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/certificates/expiring")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_certificate_history", description="Get certificate history.")
async def npg_get_certificate_history() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/certificates/history")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_upload_certificate", description="Upload a certificate file. Required: domain_names, cert_content, key_content.")
async def npg_upload_certificate(domain_names: list[str], cert_content: str, key_content: str) -> dict:
    try:
        _validate_required("domain_names", domain_names)
        _validate_required("cert_content", cert_content)
        _validate_required("key_content", key_content)
        c = _get_client()
        body = {"domain_names": domain_names, "certificate_pem": cert_content, "private_key_pem": key_content}
        data = c.post("/api/v1/certificates/upload", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── URI Blocks ─────────────────────────────────────────────────────────

@mcp.tool(name="npg_list_uri_blocks", description="List all URI blocks (global and per-host).")
async def npg_list_uri_blocks() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/uri-blocks")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_bulk_add_uri_block_rule", description="Bulk add a URI block rule to multiple or all proxy hosts. REQUIRED: pattern. Optional: match_type ('exact'/'prefix'/'regex', default 'exact'), description, host_ids (list of host UUIDs; empty = all enabled hosts).")
async def npg_bulk_add_uri_block_rule(pattern: str, match_type: str = "exact", description: str | None = None, host_ids: list[str] | None = None) -> dict:
    try:
        _validate_required("pattern", pattern)
        c = _get_client()
        # Non-standard: pre-seeded required fields + conditional — kept as-is (not _build_body).
        body: dict = {"pattern": pattern, "match_type": match_type}
        if description is not None:
            body["description"] = description
        if host_ids is not None:
            body["host_ids"] = host_ids
        data = c.post("/api/v1/uri-blocks/bulk-add-rule", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Global URI Block ───────────────────────────────────────────────────

@mcp.tool(name="npg_get_global_uri_block", description="GET global URI block configuration.")
async def npg_get_global_uri_block() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/global-uri-block")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_uri_block", description="UPDATE global URI block configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips.")
async def npg_update_global_uri_block(enabled: bool | None = None, rules: list[dict] | None = None, exception_ips: list[str] | None = None, allow_private_ips: bool | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "rules": "rules",
                "exception_ips": "exception_ips",
                "allow_private_ips": "allow_private_ips",
            },
        )
        data = c.put("/api/v1/global-uri-block", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_global_uri_block_rule", description="ADD a rule to the global URI block. REQUIRED: pattern. Optional: match_type (exact/prefix/regex, default prefix), description, enabled (default true).")
async def npg_add_global_uri_block_rule(pattern: str, match_type: str = "prefix", description: str = "", enabled: bool | None = None) -> dict:
    try:
        _validate_required("pattern", pattern)
        c = _get_client()
        # Non-standard: pre-seeded required fields + truthy-description conditional — kept as-is (not _build_body).
        body: dict = {"pattern": pattern, "match_type": match_type}
        if description: body["description"] = description
        if enabled is not None: body["enabled"] = enabled
        data = c.post("/api/v1/global-uri-block/rules", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_global_uri_block_rule", description="Delete a rule from the global URI block by its ID. REQUIRED: rule_id.")
async def npg_delete_global_uri_block_rule(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        c.delete(f"/api/v1/global-uri-block/rules/{_id_path(rule_id)}")
        return {"success": True, "message": f"Global URI block rule {_id_path(rule_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Upstream Health ────────────────────────────────────────────────────

@mcp.tool(name="npg_get_upstream_health", description="GET health status of an upstream pool. REQUIRED: upstream_id (UUID string).")
async def npg_get_upstream_health(upstream_id: str) -> dict:
    try:
        _validate_id("upstream_id", upstream_id)
        c = _get_client()
        data = c.get(f"/api/v1/upstreams/{_id_path(upstream_id)}/health")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Cloud Providers by Region ──────────────────────────────────────────

@mcp.tool(name="npg_list_cloud_providers_by_region", description="List cloud providers filtered by region.")
async def npg_list_cloud_providers_by_region(region: str | None = None) -> dict:
    c = _get_client()
    try:
        params = {"region": region} if region else None
        data = c.get("/api/v1/cloud-providers/by-region", params=params)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Catalog ────────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_catalog", description="Get the curated filter subscription catalog. Returns metadata (name, description, type, path, entry count) from the public npg-filters index — no entries or database rows.")
async def npg_get_catalog() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/filter-subscriptions/catalog")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Docker Containers ──────────────────────────────────────────────────

@mcp.tool(name="npg_get_docker_containers", description="Get status of all Docker containers managed by NPG.")
async def npg_get_docker_containers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/docker/containers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Update Check ───────────────────────────────────────────────────────

@mcp.tool(name="npg_check_update", description="Check for available NPG updates.")
async def npg_check_update() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-settings/update/check")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── ACME Test ──────────────────────────────────────────────────────────

@mcp.tool(name="npg_test_acme", description="Test ACME configuration for DNS provider.")
async def npg_test_acme(dns_provider_id: str | int | None = None) -> dict:
    c = _get_client()
    try:
        body = {"dns_provider_id": _id_path(dns_provider_id)} if dns_provider_id is not None else {}
        data = c.post("/api/v1/system-settings/acme/test", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Public UI Settings ─────────────────────────────────────────────────

@mcp.tool(name="npg_get_public_ui_settings", description="Get public UI settings (accessible without auth).")
async def npg_get_public_ui_settings() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/public/ui-settings")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Dashboard ──────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_dashboard_containers", description="Get Docker container statistics for the dashboard.")
async def npg_get_dashboard_containers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dashboard/containers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_dashboard_stats", description="Get hourly statistics for the dashboard.")
async def npg_get_dashboard_stats() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dashboard/stats/hourly")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_dashboard_health_history", description="Get system health history for the dashboard.")
async def npg_get_dashboard_health_history() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dashboard/health/history")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Cloudflare Tunnel ──────────────────────────────────────────────────

@mcp.tool(name="npg_get_cloudflare_tunnel", description="Get Cloudflare Tunnel configuration.")
async def npg_get_cloudflare_tunnel() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/cloudflare-tunnel")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_cloudflare_tunnel", description="Update Cloudflare Tunnel configuration. Pass only fields to change.")
async def npg_update_cloudflare_tunnel(kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put("/api/v1/settings/cloudflare-tunnel", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_cloudflare_tunnel_status", description="Get Cloudflare Tunnel status.")
async def npg_get_cloudflare_tunnel_status() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/cloudflare-tunnel/status")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Global Security Headers ────────────────────────────────────────────

@mcp.tool(name="npg_get_global_security_headers", description="GET global security headers configuration.")
async def npg_get_global_security_headers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/global-security-headers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_security_headers", description="UPDATE global security headers configuration (partial update). Optional: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options, x_content_type_options, x_xss_protection, referrer_policy, content_security_policy.")
async def npg_update_global_security_headers(enabled: bool | None = None, hsts_enabled: bool | None = None, hsts_max_age: int | None = None, hsts_include_subdomains: bool | None = None, hsts_preload: bool | None = None, x_frame_options: str | None = None, x_content_type_options: bool | None = None, x_xss_protection: bool | None = None, referrer_policy: str | None = None, content_security_policy: str | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "hsts_enabled": "hsts_enabled",
                "hsts_max_age": "hsts_max_age",
                "hsts_include_subdomains": "hsts_include_subdomains",
                "hsts_preload": "hsts_preload",
                "x_frame_options": "x_frame_options",
                "x_content_type_options": "x_content_type_options",
                "x_xss_protection": "x_xss_protection",
                "referrer_policy": "referrer_policy",
                "content_security_policy": "content_security_policy",
            },
        )
        data = c.put("/api/v1/settings/global-security-headers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Global Bot Filter ──────────────────────────────────────────────────

@mcp.tool(name="npg_get_global_bot_filter", description="GET global bot filter configuration.")
async def npg_get_global_bot_filter() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/global-bot-filter")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_bot_filter", description="UPDATE global bot filter configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, block_bad_bots, block_ai_bots, allow_search_engines, block_suspicious_clients, challenge_suspicious, custom_blocked_agents, custom_allowed_agents.")
async def npg_update_global_bot_filter(enabled: bool | None = None, block_bad_bots: bool | None = None, block_ai_bots: bool | None = None, allow_search_engines: bool | None = None, block_suspicious_clients: bool | None = None, challenge_suspicious: bool | None = None, custom_blocked_agents: str | None = None, custom_allowed_agents: str | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "block_bad_bots": "block_bad_bots",
                "block_ai_bots": "block_ai_bots",
                "allow_search_engines": "allow_search_engines",
                "block_suspicious_clients": "block_suspicious_clients",
                "challenge_suspicious": "challenge_suspicious",
                "custom_blocked_agents": "custom_blocked_agents",
                "custom_allowed_agents": "custom_allowed_agents",
            },
        )
        data = c.put("/api/v1/settings/global-bot-filter", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Global Cloud Providers ─────────────────────────────────────────────

@mcp.tool(name="npg_get_global_cloud_providers", description="GET global cloud providers configuration.")
async def npg_get_global_cloud_providers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/global-cloud-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_cloud_providers", description="UPDATE global cloud providers configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool).")
async def npg_update_global_cloud_providers(blocked_providers: list[str] | None = None, challenge_mode: bool | None = None, allow_search_bots: bool | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "blocked_providers": "blocked_providers",
                "challenge_mode": "challenge_mode",
                "allow_search_bots": "allow_search_bots",
            },
        )
        data = c.put("/api/v1/settings/global-cloud-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Global Geo ─────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_global_geo", description="GET global GeoIP restriction configuration.")
async def npg_get_global_geo() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/global-geo")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_geo", description="UPDATE global GeoIP restriction (partial update; global default inherited by hosts without their own override). Optional: enabled, mode (whitelist/blacklist), countries (ISO codes), allowed_ips, allow_private_ips, allow_search_bots, challenge_mode.")
async def npg_update_global_geo(enabled: bool | None = None, mode: Literal["whitelist", "blacklist"] | None = None, countries: list[str] | None = None, allowed_ips: list[str] | None = None, allow_private_ips: bool | None = None, allow_search_bots: bool | None = None, challenge_mode: bool | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "mode": "mode",
                "countries": "countries",
                "allowed_ips": "allowed_ips",
                "allow_private_ips": "allow_private_ips",
                "allow_search_bots": "allow_search_bots",
                "challenge_mode": "challenge_mode",
            },
        )
        data = c.put("/api/v1/settings/global-geo", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Global Rate Limit ──────────────────────────────────────────────────

@mcp.tool(name="npg_get_global_rate_limit", description="GET global rate limit configuration.")
async def npg_get_global_rate_limit() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/global-rate-limit")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_rate_limit", description="UPDATE global rate limit configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, requests_per_second, burst_size, zone_size, limit_by, limit_response, whitelist_ips (omit=keep stored list, \"\"=clear; IP/CIDR entries, invalid 400).")
async def npg_update_global_rate_limit(enabled: bool | None = None, requests_per_second: int | None = None, burst_size: int | None = None, zone_size: str | None = None, limit_by: str | None = None, limit_response: int | None = None, whitelist_ips: str | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "requests_per_second": "requests_per_second",
                "burst_size": "burst_size",
                "zone_size": "zone_size",
                "limit_by": "limit_by",
                "limit_response": "limit_response",
                "whitelist_ips": "whitelist_ips",
            },
        )
        data = c.put("/api/v1/settings/global-rate-limit", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Global WAF ─────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_global_waf", description="GET global WAF configuration.")
async def npg_get_global_waf() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/global-waf")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_waf", description="UPDATE global WAF configuration (partial update). Optional: enabled, mode (detection|blocking), paranoia_level (1-4), anomaly_threshold. NOTE: per-host WAF changes require npg_sync_nginx; WAF changes take effect after a proxy container restart.")
async def npg_update_global_waf(enabled: bool | None = None, mode: str | None = None, paranoia_level: int | None = None, anomaly_threshold: int | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "mode": "mode",
                "paranoia_level": "paranoia_level",
                "anomaly_threshold": "anomaly_threshold",
            },
        )
        data = c.put("/api/v1/settings/global-waf", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Backups ────────────────────────────────────────────────────────────

@mcp.tool(name="npg_download_backup", description="DOWNLOAD a backup file by its ID. REQUIRED: backup_id. Returns the raw backup content (gzip binary). Use npg_list_backups to find the ID.")
async def npg_download_backup(backup_id: str | int) -> dict:
    try:
        _validate_id("backup_id", backup_id)
        c = _get_client()
        data = c.get_text(f"/api/v1/backups/{_id_path(backup_id)}/download")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_upload_restore_backup", description="UPLOAD and restore from a backup file (multipart form upload). REQUIRED: file_content (.tar.gz backup file content) and encoding ('base64' or 'raw', default 'base64') telling how file_content is encoded. With encoding='raw', file_content is sent byte-for-byte as UTF-8. The API expects a multipart 'backup' field with a .tar.gz file. Use npg_create_backup + npg_download_backup to get a backup file first.")
async def npg_upload_restore_backup(file_content: str, encoding: str = "base64") -> dict:
    try:
        _validate_required("file_content", file_content)
        if encoding not in ("base64", "raw"):
            return {"success": False, "error": f"Invalid encoding '{encoding}': must be 'base64' or 'raw'"}
        c = _get_client()
        import base64
        # Explicit encoding — no trial decode. base64.b64decode accepts most
        # byte sequences, so trial-decoding raw backups silently corrupts them.
        if encoding == "base64":
            try:
                raw = base64.b64decode(file_content, validate=True)
            except Exception as e:
                return {"success": False, "error": f"file_content is not valid base64 (encoding='base64'): {e}"}
        else:
            raw = file_content.encode("utf-8")
        data = c.post_file("/api/v1/backups/upload-restore", "backup", raw, "restore.tar.gz")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_backup_stats", description="Get backup statistics.")
async def npg_get_backup_stats() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/backups/stats")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _bearer_auth_middleware(app, expected_token: str):
    """Require a bearer Authorization header on every request except /health.

    Returns the app unchanged if no MCP_API_TOKEN is configured (open mode,
    for local/LAN-only use). When set, unauthenticated/non-matching requests
    get a 401 and are never forwarded to MCP. The unauthenticated /health
    route (added by _health_app before this middleware wraps the app) is the
    single exception — a container healthcheck cannot carry MCP_API_TOKEN.
    """
    if not expected_token:
        return app

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    expected_bearer = f"Bearer {expected_token}"

    class _AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            auth = request.headers.get("authorization", "")
            if not hmac.compare_digest(auth, expected_bearer):
                return JSONResponse(
                    {"error": "unauthorized: invalid or missing bearer token"},
                    status_code=401,
                )
            return await call_next(request)

    return _AuthMiddleware(app)

"""Additional MCP tools — to be inserted into main.py before def main()."""


# ── Auth Extras ────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_auth_status", description="GET authentication status — returns whether the current session is authenticated and basic user info.")
async def npg_get_auth_status() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/auth/status")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_auth_me", description="GET the current authenticated identity — returns the token owner's info and effective_permissions (token scopes ∩ owner role). Use to check what the current API token can actually do.")
async def npg_get_auth_me() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/auth/me")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_auth_sso_providers", description="List SSO providers available for the login screen (public-facing).")
async def npg_get_auth_sso_providers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/auth/sso/providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_auth_sso_start", description="Begin an SSO login flow. REQUIRED: slug (the SSO provider identifier). Returns the identity provider redirect URL (Location header from the NPG API's 302 response) as {\"redirect_url\": ...}.")
async def npg_auth_sso_start(slug: str) -> dict:
    try:
        _validate_id("slug", slug)
        c = _get_client()
        data = c.get(f"/api/v1/auth/sso/{quote(slug, safe='')}/start", redirect_ok=True)
        if data is not None and "redirect_url" in data:
            return {"success": True, "redirect_url": data["redirect_url"]}
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Auth Providers (ForwardAuth) ───────────────────────────────────────

@mcp.tool(name="npg_list_auth_providers", description="List ForwardAuth (Authelia, Authentik, custom) providers.")
async def npg_list_auth_providers() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/auth-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_auth_provider", description="CREATE a ForwardAuth provider. REQUIRED: name, provider_type (authelia/authentik/custom), provider_url (http(s) URL). Optional: config (dict), enabled, timeout_ms, container_name, container_network, container_port, container_scheme (Docker-backed: provider_url resolved from container).")
async def npg_create_auth_provider(name: str, provider_type: str, provider_url: str | None = None, config: dict | None = None, enabled: bool | None = None, timeout_ms: int | None = None, container_name: str | None = None, container_network: str | None = None, container_port: int | None = None, container_scheme: str | None = None) -> dict:
    try:
        _validate_required("name", name)
        _validate_required("provider_type", provider_type)
        c = _get_client()
        # Non-standard: pre-seeded required fields + param->API rename (provider_type -> type) — kept as-is (not _build_body).
        body: dict = {"name": name, "type": provider_type}
        if provider_url is not None: body["provider_url"] = provider_url
        if config is not None: body["config"] = config
        if enabled is not None: body["enabled"] = enabled
        if timeout_ms is not None: body["timeout_ms"] = timeout_ms
        if container_name is not None: body["container_name"] = container_name
        if container_network is not None: body["container_network"] = container_network
        if container_port is not None: body["container_port"] = container_port
        if container_scheme is not None: body["container_scheme"] = container_scheme
        data = c.post("/api/v1/auth-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_auth_provider", description="Get a ForwardAuth provider by its ID. REQUIRED: provider_id.")
async def npg_get_auth_provider(provider_id: str | int) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        data = c.get(f"/api/v1/auth-providers/{_id_path(provider_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_auth_provider", description="UPDATE a ForwardAuth provider (partial update — omitted fields left as-is). REQUIRED: provider_id. Optional: name, provider_url, config (dict), enabled, timeout_ms, container_name, container_network, container_port, container_scheme.")
async def npg_update_auth_provider(provider_id: str | int, name: str | None = None, provider_url: str | None = None, config: dict | None = None, enabled: bool | None = None, timeout_ms: int | None = None, container_name: str | None = None, container_network: str | None = None, container_port: int | None = None, container_scheme: str | None = None) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "name": "name",
                "provider_url": "provider_url",
                "config": "config",
                "enabled": "enabled",
                "timeout_ms": "timeout_ms",
                "container_name": "container_name",
                "container_network": "container_network",
                "container_port": "container_port",
                "container_scheme": "container_scheme",
            },
        )
        data = c.put(f"/api/v1/auth-providers/{_id_path(provider_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_auth_provider", description="Delete a ForwardAuth provider by its ID. REQUIRED: provider_id.")
async def npg_delete_auth_provider(provider_id: str | int) -> dict:
    try:
        _validate_id("provider_id", provider_id)
        c = _get_client()
        c.delete(f"/api/v1/auth-providers/{_id_path(provider_id)}")
        return {"success": True, "message": f"Auth provider {_id_path(provider_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── DDNS Records ───────────────────────────────────────────────────────

@mcp.tool(name="npg_list_ddns_records", description="List all DDNS records.")
async def npg_list_ddns_records() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/ddns-records")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_ddns_record", description="CREATE a DDNS record. REQUIRED: hostname (the DDNS domain to keep updated), dns_provider_id (UUID of a Cloudflare/DuckDNS/Dynu DNS provider). Optional: proxied (bool, Cloudflare only), ttl (int, Cloudflare: 1=auto), enabled (bool).")
async def npg_create_ddns_record(hostname: str, dns_provider_id: str | int, proxied: bool = False, ttl: int = 0, enabled: bool = True) -> dict:
    try:
        _validate_required("hostname", hostname)
        _validate_id("dns_provider_id", dns_provider_id)
        c = _get_client()
        body = {"hostname": hostname, "dns_provider_id": _id_path(dns_provider_id), "proxied": proxied, "ttl": ttl, "enabled": enabled}
        data = c.post("/api/v1/ddns-records", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_ddns_record", description="Get a DDNS record by its ID. REQUIRED: record_id.")
async def npg_get_ddns_record(record_id: str | int) -> dict:
    try:
        _validate_id("record_id", record_id)
        c = _get_client()
        data = c.get(f"/api/v1/ddns-records/{_id_path(record_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_ddns_record", description="UPDATE a DDNS record (partial update — omitted fields left as-is). REQUIRED: record_id. Optional: hostname, dns_provider_id, proxied (bool), ttl (int), enabled (bool).")
async def npg_update_ddns_record(record_id: str | int, hostname: str | None = None, dns_provider_id: str | int | None = None, proxied: bool | None = None, ttl: int | None = None, enabled: bool | None = None) -> dict:
    try:
        _validate_id("record_id", record_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {
                "hostname": "hostname",
                "dns_provider_id": "dns_provider_id",
                "proxied": "proxied",
                "ttl": "ttl",
                "enabled": "enabled",
            },
            id_fields={"dns_provider_id"},
        )
        data = c.put(f"/api/v1/ddns-records/{_id_path(record_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_ddns_record", description="Delete a DDNS record by its ID. REQUIRED: record_id.")
async def npg_delete_ddns_record(record_id: str | int) -> dict:
    try:
        _validate_id("record_id", record_id)
        c = _get_client()
        c.delete(f"/api/v1/ddns-records/{_id_path(record_id)}")
        return {"success": True, "message": f"DDNS record {_id_path(record_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_sync_ddns_records", description="Sync all enabled DDNS records now (force immediate DNS update for all records).")
async def npg_sync_ddns_records() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/ddns-records/sync")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_sync_ddns_record", description="Sync one DDNS record now (force DNS update for a specific record). REQUIRED: record_id.")
async def npg_sync_ddns_record(record_id: str | int) -> dict:
    try:
        _validate_id("record_id", record_id)
        c = _get_client()
        data = c.post(f"/api/v1/ddns-records/{_id_path(record_id)}/sync")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_import_ddns_from_hosts", description="Import DDNS records from existing proxy hosts that have DDNS enabled. REQUIRED: proxy_host_ids (list of host UUIDs), dns_provider_id (UUID of the DNS provider to use).")
async def npg_import_ddns_from_hosts(proxy_host_ids: list[str], dns_provider_id: str) -> dict:
    try:
        _validate_required("proxy_host_ids", proxy_host_ids)
        _validate_id("dns_provider_id", dns_provider_id)
        c = _get_client()
        body = {"proxy_host_ids": proxy_host_ids, "dns_provider_id": _id_path(dns_provider_id)}
        data = c.post("/api/v1/ddns-records/import-from-hosts", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Filter Subscriptions ───────────────────────────────────────────────

@mcp.tool(name="npg_list_filter_subscriptions", description="List all filter subscriptions (remote IP/UA blocklists).")
async def npg_list_filter_subscriptions() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/filter-subscriptions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_subscribe_filter_catalog", description="Subscribe to one or more catalog filter lists. REQUIRED: paths (list of catalog list paths, e.g. 'lists/ips/web-scanners.json').")
async def npg_subscribe_filter_catalog(paths: list[str]) -> dict:
    try:
        _validate_required("paths", paths)
        c = _get_client()
        data = c.post("/api/v1/filter-subscriptions/catalog/subscribe", {"paths": paths})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_filter_subscription", description="Subscribe to a filter list URL. REQUIRED: url. Optional: name.")
async def npg_create_filter_subscription(url: str, name: str | None = None) -> dict:
    try:
        _validate_required("url", url)
        c = _get_client()
        body = {"url": url}
        if name is not None:
            body["name"] = name
        data = c.post("/api/v1/filter-subscriptions", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_filter_subscription", description="Get a filter subscription with its entries and exclusions. REQUIRED: subscription_id.")
async def npg_get_filter_subscription(subscription_id: str | int) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        c = _get_client()
        data = c.get(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_filter_subscription", description="Update a filter subscription (partial update). Pass only fields to change. REQUIRED: subscription_id.")
async def npg_update_filter_subscription(subscription_id: str | int, name: str | None = None, url: str | None = None, enabled: bool | None = None) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {"name": "name", "url": "url", "enabled": "enabled"},
        )
        data = c.put(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_filter_subscription", description="Delete a filter subscription by its ID. REQUIRED: subscription_id.")
async def npg_delete_filter_subscription(subscription_id: str | int) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        c = _get_client()
        c.delete(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}")
        return {"success": True, "message": f"Filter subscription {_id_path(subscription_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_refresh_filter_subscription", description="Re-fetch entries for a filter subscription now. REQUIRED: subscription_id.")
async def npg_refresh_filter_subscription(subscription_id: str | int) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        c = _get_client()
        data = c.post(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/refresh")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_filter_subscription_exclusions", description="List host exclusions of a filter subscription (hosts that skip this subscription). REQUIRED: subscription_id.")
async def npg_get_filter_subscription_exclusions(subscription_id: str | int) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        c = _get_client()
        data = c.get(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/exclusions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_filter_subscription_exclusion", description="Exclude a proxy host from a filter subscription. REQUIRED: subscription_id, host_id.")
async def npg_add_filter_subscription_exclusion(subscription_id: str | int, host_id: str | int) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.post(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/exclusions/{_id_path(host_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_filter_subscription_exclusion", description="Remove a host exclusion from a filter subscription. REQUIRED: subscription_id, host_id.")
async def npg_remove_filter_subscription_exclusion(subscription_id: str | int, host_id: str | int) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/exclusions/{_id_path(host_id)}")
        return {"success": True, "message": f"Exclusion removed for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_filter_subscription_entry_exclusions", description="List entry exclusions of a filter subscription (specific entries that are skipped). REQUIRED: subscription_id.")
async def npg_get_filter_subscription_entry_exclusions(subscription_id: str | int) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        c = _get_client()
        data = c.get(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/entry-exclusions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_filter_subscription_entry_exclusion", description="Exclude a single entry value from a filter subscription. REQUIRED: subscription_id, entry_value (the entry value to exclude; sent as 'value' to the NPG API).")
async def npg_add_filter_subscription_entry_exclusion(subscription_id: str | int, entry_value: str) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        _validate_required("entry_value", entry_value)
        c = _get_client()
        data = c.post(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/entry-exclusions", {"value": entry_value})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_filter_subscription_entry_exclusion", description="Remove an entry exclusion from a filter subscription. REQUIRED: subscription_id, entry_value (the excluded entry value; sent as the 'value' query parameter to the NPG API).")
async def npg_remove_filter_subscription_entry_exclusion(subscription_id: str | int, entry_value: str) -> dict:
    try:
        _validate_id("subscription_id", subscription_id)
        _validate_required("entry_value", entry_value)
        c = _get_client()
        c.delete(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/entry-exclusions", {"value": entry_value})
        return {"success": True, "message": f"Entry exclusion removed: {entry_value}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Exploit Rules Extras ───────────────────────────────────────────────

@mcp.tool(name="npg_get_exploit_rules_hosts", description="List proxy hosts that have exploit blocking enabled.")
async def npg_get_exploit_rules_hosts() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/exploit-rules/hosts")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_exploit_rules_for_host", description="List exploit rules with this host's exclusion status. REQUIRED: host_id.")
async def npg_get_exploit_rules_for_host(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/exploit-rules/hosts/{_id_path(host_id)}/rules")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_exclude_exploit_rule_from_host", description="Exclude an exploit rule on ONE proxy host (stop it blocking there). REQUIRED: host_id, rule_id.")
async def npg_exclude_exploit_rule_from_host(host_id: str | int, rule_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.post(f"/api/v1/exploit-rules/hosts/{_id_path(host_id)}/rules/{_id_path(rule_id)}/exclude")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_exploit_rule_exclusion_from_host", description="Remove a host exclusion for an exploit rule (re-enable the rule for that host). REQUIRED: host_id, rule_id.")
async def npg_remove_exploit_rule_exclusion_from_host(host_id: str | int, rule_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_id("rule_id", rule_id)
        c = _get_client()
        c.delete(f"/api/v1/exploit-rules/hosts/{_id_path(host_id)}/rules/{_id_path(rule_id)}/exclude")
        return {"success": True, "message": f"Rule {_id_path(rule_id)} re-enabled for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_global_exclude_exploit_rule", description="Exclude an exploit rule on EVERY host (stop it blocking anywhere). REQUIRED: rule_id.")
async def npg_global_exclude_exploit_rule(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.post(f"/api/v1/exploit-rules/{_id_path(rule_id)}/global-exclude")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_exploit_rule_global_exclusion", description="Remove a global exclusion for an exploit rule (re-enable the rule everywhere). REQUIRED: rule_id.")
async def npg_remove_exploit_rule_global_exclusion(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        c.delete(f"/api/v1/exploit-rules/{_id_path(rule_id)}/global-exclude")
        return {"success": True, "message": f"Rule {_id_path(rule_id)} re-enabled globally"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Certificate Extras ─────────────────────────────────────────────────

@mcp.tool(name="npg_delete_certificate_errors", description="Bulk-delete all certificates in error status.")
async def npg_delete_certificate_errors() -> dict:
    c = _get_client()
    try:
        c.delete("/api/v1/certificates/errors")
        return {"success": True, "message": "All error certificates deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_clear_certificate_error", description="Clear a certificate's error state (mark as resolved). REQUIRED: cert_id.")
async def npg_clear_certificate_error(cert_id: str | int) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        c = _get_client()
        c.delete(f"/api/v1/certificates/{_id_path(cert_id)}/error")
        return {"success": True, "message": f"Certificate {_id_path(cert_id)} error cleared"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_upload_certificate_pem", description="Replace the PEM material of a custom certificate. REQUIRED: cert_id, pem_content (full PEM certificate string), private_key_pem (full PEM private key string). Sends certificate_pem + private_key_pem to the NPG API. After upload, verify with npg_get_certificate.")
async def npg_upload_certificate_pem(cert_id: str | int, pem_content: str, private_key_pem: str) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        _validate_required("pem_content", pem_content)
        _validate_required("private_key_pem", private_key_pem)
        c = _get_client()
        body = {"certificate_pem": pem_content, "private_key_pem": private_key_pem}
        data = c.put(f"/api/v1/certificates/{_id_path(cert_id)}/upload", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_certificate_logs", description="Get the issuance log stream for a certificate. REQUIRED: cert_id.")
async def npg_get_certificate_logs(cert_id: str | int) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        c = _get_client()
        data = c.get(f"/api/v1/certificates/{_id_path(cert_id)}/logs")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_certificate_download", description="Download certificate material (PEM/zip). REQUIRED: cert_id. Returns the raw content.")
async def npg_get_certificate_download(cert_id: str | int) -> dict:
    try:
        _validate_id("cert_id", cert_id)
        c = _get_client()
        data = c.get_text(f"/api/v1/certificates/{_id_path(cert_id)}/download")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Challenge Config ───────────────────────────────────────────────────

@mcp.tool(name="npg_get_challenge_config", description="GET the global CAPTCHA challenge configuration.")
async def npg_get_challenge_config() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/challenge-config")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_challenge_config", description="UPDATE the global CAPTCHA challenge configuration (partial update). Pass only fields to change.")
async def npg_update_challenge_config(enabled: bool | None = None, provider: str | None = None, secret_key: str | None = None, site_key: str | None = None, challenge_type: str | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {
                "enabled": "enabled",
                "provider": "provider",
                "secret_key": "secret_key",
                "site_key": "site_key",
                "challenge_type": "challenge_type",
            },
        )
        data = c.put("/api/v1/challenge-config", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_challenge_stats", description="GET CAPTCHA challenge statistics.")
async def npg_get_challenge_stats() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/challenge-config/stats")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── DNS Providers Extras ───────────────────────────────────────────────

@mcp.tool(name="npg_get_dns_provider_default", description="Get the default DNS provider for certificate issuance.")
async def npg_get_dns_provider_default() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/dns-providers/default")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Logs Extras ────────────────────────────────────────────────────────

@mcp.tool(name="npg_post_log", description="Insert a log entry manually. REQUIRED: level, message. Optional: source, component, tags.")
async def npg_post_log(level: str, message: str, source: str | None = None, component: str | None = None, log_type: str = "access") -> dict:
    try:
        _validate_required("level", level)
        _validate_required("message", message)
        c = _get_client()
        # Non-standard: pre-seeded required fields + conditional — kept as-is (not _build_body).
        body = {"level": level, "message": message, "log_type": log_type}
        if source is not None: body["source"] = source
        if component is not None: body["component"] = component
        data = c.post("/api/v1/logs", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_cleanup_logs", description="Delete nginx access logs older than the configured retention period.")
async def npg_cleanup_logs() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/logs/cleanup")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_autocomplete_hosts", description="Get distinct hosts seen in nginx access logs (for autocomplete).")
async def npg_get_log_autocomplete_hosts() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/autocomplete/hosts")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_autocomplete_ips", description="Get distinct client IPs seen in nginx access logs (for autocomplete).")
async def npg_get_log_autocomplete_ips() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/autocomplete/ips")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_autocomplete_user_agents", description="Get distinct User-Agents seen in nginx access logs (for autocomplete).")
async def npg_get_log_autocomplete_user_agents() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/autocomplete/user-agents")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_autocomplete_uris", description="Get distinct request URIs seen in nginx access logs (for autocomplete).")
async def npg_get_log_autocomplete_uris() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/autocomplete/uris")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_autocomplete_countries", description="Get distinct countries seen in nginx access logs (for autocomplete).")
async def npg_get_log_autocomplete_countries() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/autocomplete/countries")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_autocomplete_methods", description="Get distinct HTTP methods seen in nginx access logs (for autocomplete).")
async def npg_get_log_autocomplete_methods() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs/autocomplete/methods")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_log_filter_presets", description="List saved log filter presets.")
async def npg_get_log_filter_presets() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/log-filter-presets")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_log_filter_preset", description="Save a log filter preset. REQUIRED: name, filter (dict). Optional: description.")
async def npg_create_log_filter_preset(name: str, filter: dict, description: str | None = None) -> dict:
    try:
        _validate_required("name", name)
        _validate_required("filter", filter)
        c = _get_client()
        body = {"name": name, "filter": filter}
        if description is not None:
            body["description"] = description
        data = c.post("/api/v1/log-filter-presets", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_log_filter_preset", description="Update a log filter preset (rename and/or replace filter). REQUIRED: preset_id. Optional: name, filter, description.")
async def npg_update_log_filter_preset(preset_id: str | int, name: str | None = None, filter: dict | None = None, description: str | None = None) -> dict:
    try:
        _validate_id("preset_id", preset_id)
        c = _get_client()
        body = _build_body(
            locals(),
            {"name": "name", "filter": "filter", "description": "description"},
        )
        data = c.put(f"/api/v1/log-filter-presets/{_id_path(preset_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_log_filter_preset", description="Delete a log filter preset by its ID. REQUIRED: preset_id.")
async def npg_delete_log_filter_preset(preset_id: str | int) -> dict:
    try:
        _validate_id("preset_id", preset_id)
        c = _get_client()
        c.delete(f"/api/v1/log-filter-presets/{_id_path(preset_id)}")
        return {"success": True, "message": f"Log filter preset {_id_path(preset_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_cleanup_system_logs", description="Delete old system logs beyond the configured retention period.")
async def npg_cleanup_system_logs() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/system-logs/cleanup")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_system_log_sources", description="Get selectable system log sources (docker_api, docker_nginx, health_check, etc.).")
async def npg_get_system_log_sources() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-logs/sources")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_system_log_levels", description="Get selectable system log levels (debug, info, warn, error, fatal).")
async def npg_get_system_log_levels() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-logs/levels")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_system_log_stats", description="Get system log statistics (counts by source/level).")
async def npg_get_system_log_stats() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-logs/stats")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_system_settings_logs", description="Get the container log collector configuration.")
async def npg_get_system_settings_logs() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-settings/logs")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_system_settings_logs", description="Update the container log collector configuration (partial update). Pass only fields to change.")
async def npg_update_system_settings_logs(max_age: str | None = None, max_size: str | None = None, max_files: int | None = None) -> dict:
    c = _get_client()
    try:
        body = _build_body(
            locals(),
            {"max_age": "max_age", "max_size": "max_size", "max_files": "max_files"},
        )
        data = c.put("/api/v1/system-settings/logs", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_audit_log_actions", description="List the action values present in the audit log (for filtering).")
async def npg_get_audit_log_actions() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/audit-logs/actions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_audit_log_resource_types", description="List the resource types present in the audit log (for filtering).")
async def npg_get_audit_log_resource_types() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/audit-logs/resource-types")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_audit_log_api_tokens", description="List recent API token usage across all tokens.")
async def npg_get_audit_log_api_tokens() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/audit-logs/api-tokens")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Proxy Host Extras ──────────────────────────────────────────────────

@mcp.tool(name="npg_set_proxy_host_favorite", description="Toggle a proxy host as a favorite. REQUIRED: host_id, favorite (bool).")
async def npg_set_proxy_host_favorite(host_id: str | int, favorite: bool) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_required("favorite", favorite)
        c = _get_client()
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/favorite", {"favorite": favorite})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(name="npg_sync_redirect_hosts", description="Regenerate every redirect host config and reload nginx.")
async def npg_sync_redirect_hosts() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/redirect-hosts/sync")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── SSO Extras ─────────────────────────────────────────────────────────
@mcp.tool(name="npg_delete_proxy_host_rate_limit", description="Delete the rate limit config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_rate_limit(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit")
        return {"success": True, "message": f"Rate limit deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_bot_filter", description="Delete the bot filter config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_bot_filter(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter")
        return {"success": True, "message": f"Bot filter deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_security_headers", description="Delete the security headers config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_security_headers(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers")
        return {"success": True, "message": f"Security headers deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_upstream", description="Delete the upstream/load balancing config for a proxy host — host falls back to defaults. REQUIRED: host_id.")
async def npg_delete_proxy_host_upstream(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream")
        return {"success": True, "message": f"Upstream config deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_uri_block", description="Delete the URI block config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_uri_block(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block")
        return {"success": True, "message": f"URI block deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_fail2ban", description="Delete the fail2ban config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_fail2ban(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban")
        return {"success": True, "message": f"Fail2ban config deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_bulk_unban_ips", description="Unban multiple banned-IP records at once. REQUIRED: ids (list of record IDs).")
async def npg_bulk_unban_ips(ids: list[str | int]) -> dict:
    try:
        _validate_required("ids", ids)
        c = _get_client()
        data = c.post("/api/v1/banned-ips/bulk-unban", {"ids": [_id_path(i) for i in ids]})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_ban_history", description="Get ban/unban event history.")
async def npg_get_ban_history() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/banned-ips/history")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_ban_history_stats", description="Get ban/unban history statistics.")
async def npg_get_ban_history_stats() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/banned-ips/history/stats")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_ban_history_for_ip", description="Get ban history for a specific IP address. REQUIRED: ip.")
async def npg_get_ban_history_for_ip(ip: str) -> dict:
    try:
        _validate_required("ip", ip)
        c = _get_client()
        data = c.get(f"/api/v1/banned-ips/history/ip/{quote(ip, safe='')}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_ip_traffic_stats", description="Get traffic and ban summary for one IP address. Returns geolocation, request volume, top hosts/URIs, and ban counts. REQUIRED: ip. Optional: days (window for traffic figures — must be 1, 7, or 30; defaults to server default).")
async def npg_get_ip_traffic_stats(ip: str, days: int | None = None) -> dict:
    try:
        _validate_required("ip", ip)
        c = _get_client()
        params: dict = {}
        if days is not None:
            params["days"] = days
        data = c.get(f"/api/v1/banned-ips/stats/ip/{quote(ip, safe='')}", params=params or None)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_proxy_host_uri_block_rule", description="Add a single URI block rule to a proxy host. REQUIRED: host_id, pattern (str or regex). Optional: match_type ('exact'/'prefix'/'regex', default 'prefix'), description.")
async def npg_add_proxy_host_uri_block_rule(host_id: str | int, pattern: str, match_type: str = "prefix", description: str | None = None) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_required("pattern", pattern)
        c = _get_client()
        # Non-standard: pre-seeded required fields + conditional — kept as-is (not _build_body).
        body: dict = {"pattern": pattern, "match_type": match_type}
        if description is not None:
            body["description"] = description
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block/rules", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_uri_block_rule", description="Remove a single URI block rule from a proxy host. REQUIRED: host_id, rule_id.")
async def npg_delete_proxy_host_uri_block_rule(host_id: str | int, rule_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_id("rule_id", rule_id)
        c = _get_client()
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block/rules/{_id_path(rule_id)}")
        return {"success": True, "message": f"URI block rule {_id_path(rule_id)} deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Settings Extras ────────────────────────────────────────────────────

@mcp.tool(name="npg_reset_settings", description="Reset global nginx settings to defaults. DESTRUCTIVE — this clears all custom settings.")
async def npg_reset_settings() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/settings/reset")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_settings_presets", description="List available global settings presets that can be applied.")
async def npg_get_settings_presets() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/settings/presets")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_apply_settings_preset", description="Apply a global settings preset. REQUIRED: preset (preset name/identifier).")
async def npg_apply_settings_preset(preset: str) -> dict:
    try:
        _validate_required("preset", preset)
        c = _get_client()
        data = c.post(f"/api/v1/settings/preset/{quote(preset, safe='')}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── System Extras ──────────────────────────────────────────────────────

@mcp.tool(name="npg_get_health_detailed", description="GET a detailed health snapshot (detailed version of health check).")
async def npg_get_health_detailed() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/health/detailed")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_status", description="GET component status — health of all NPG subsystems (API, database, nginx).")
async def npg_get_status() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/status")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_permission_areas", description="Get the permission area/verb matrix — all available permission scopes.")
async def npg_get_permission_areas() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/permission-areas")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_waf_global_rules", description="List all OWASP CRS rules with their GLOBAL exclusion status.")
async def npg_get_waf_global_rules() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/waf/global/rules")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_waf_global_exclusions", description="List the globally disabled CRS rules.")
async def npg_get_waf_global_exclusions() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/waf/global/exclusions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_waf_global_history", description="Get the global WAF policy change history.")
async def npg_get_waf_global_history() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/waf/global/history")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_disable_waf_global_rule", description="Disable a CRS rule for EVERY host (globally). REQUIRED: rule_id.")
async def npg_disable_waf_global_rule(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.post(f"/api/v1/waf/global/rules/{_id_path(rule_id)}/disable")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_enable_waf_global_rule", description="Re-enable a CRS rule globally (remove global disable). REQUIRED: rule_id.")
async def npg_enable_waf_global_rule(rule_id: str | int) -> dict:
    try:
        _validate_id("rule_id", rule_id)
        c = _get_client()
        c.delete(f"/api/v1/waf/global/rules/{_id_path(rule_id)}/disable")
        return {"success": True, "message": f"WAF rule {_id_path(rule_id)} re-enabled globally"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_waf_host_history", description="Get the WAF policy change history for a proxy host. REQUIRED: host_id.")
async def npg_get_waf_host_history(host_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        c = _get_client()
        data = c.get(f"/api/v1/waf/hosts/{_id_path(host_id)}/history")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_disable_waf_rule_by_host", description="Disable a CRS rule on the host that owns a domain name. REQUIRED: domain_name (the host's domain), rule_id (CRS rule ID, e.g. 200000). Sends host + rule_id (int) to the API.")
async def npg_disable_waf_rule_by_host(domain_name: str, rule_id: str | int) -> dict:
    try:
        _validate_required("domain_name", domain_name)
        _validate_id("rule_id", rule_id)
        c = _get_client()
        data = c.post("/api/v1/waf/rules/disable-by-host", {"host": domain_name, "rule_id": int(rule_id)})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_enable_waf_rule_by_host", description="Re-enable a CRS rule for a specific proxy host (removes per-host exclusion). REQUIRED: host_id (proxy host UUID), rule_id (CRS rule ID).")
async def npg_enable_waf_rule_by_host(host_id: str | int, rule_id: str | int) -> dict:
    try:
        _validate_id("host_id", host_id)
        _validate_id("rule_id", rule_id)
        c = _get_client()
        c.delete(f"/api/v1/waf/hosts/{_id_path(host_id)}/rules/{_id_path(rule_id)}/disable")
        return {"success": True, "message": f"WAF rule {_id_path(rule_id)} re-enabled for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── API Tokens Extras ──────────────────────────────────────────────────

@mcp.tool(name="npg_get_api_token_permissions", description="List the permission strings an API token may carry (reference list).")
async def npg_get_api_token_permissions() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/api-tokens/permissions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_api_token_usage", description="Get recent usage for an API token. REQUIRED: token_id.")
async def npg_get_api_token_usage(token_id: str | int) -> dict:
    try:
        _validate_id("token_id", token_id)
        c = _get_client()
        data = c.get(f"/api/v1/api-tokens/{_id_path(token_id)}/usage")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── WAF Test ───────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_waf_test_patterns", description="List the built-in WAF attack test patterns.")
async def npg_get_waf_test_patterns() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/waf-test/patterns")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_waf_pattern", description="Fire one attack payload at a target URL for WAF testing. REQUIRED: target_url, attack_type (attack type name or index).")
async def npg_test_waf_pattern(target_url: str, attack_type: str) -> dict:
    try:
        _validate_required("target_url", target_url)
        _validate_required("attack_type", attack_type)
        c = _get_client()
        data = c.post("/api/v1/waf-test/test", {"target_url": target_url, "attack_type": attack_type})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_waf_all_patterns", description="Fire every attack payload at a target URL for comprehensive WAF testing. REQUIRED: target_url.")
async def npg_test_waf_all_patterns(target_url: str) -> dict:
    try:
        _validate_required("target_url", target_url)
        c = _get_client()
        data = c.post("/api/v1/waf-test/test-all", {"target_url": target_url})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── GeoIP History ──────────────────────────────────────────────────────

@mcp.tool(name="npg_get_geoip_history", description="List GeoIP database update runs and their status.")
async def npg_get_geoip_history() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-settings/geoip/history")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Users Extras ───────────────────────────────────────────────────────
@mcp.tool(name="npg_set_user_role", description="Assign a role to a user account. REQUIRED: user_id, role_id.")
async def npg_set_user_role(user_id: str | int, role_id: str | int) -> dict:
    try:
        _validate_id("user_id", user_id)
        _validate_id("role_id", role_id)
        c = _get_client()
        data = c.put(f"/api/v1/users/{_id_path(user_id)}/role", {"role_id": _id_path(role_id)})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_set_user_email", description="Set the SSO linking email for a user account. This is the address an identity provider's verified email is matched against when linking a sign-in to an existing account. REQUIRED: user_id, email (must be a plain email address, no display name).")
async def npg_set_user_email(user_id: str | int, email: str) -> dict:
    try:
        _validate_id("user_id", user_id)
        _validate_required("email", email)
        c = _get_client()
        c.put(f"/api/v1/users/{_id_path(user_id)}/email", {"email": email})
        return {"success": True, "message": f"Email updated for user {_id_path(user_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def main() -> None:
    _setup_logging()
    # Apply the layered toolset filter (NPG_TOOL_LEVEL) before the server
    # starts. Hidden tools are removed from the FastMCP tool manager, so they
    # are neither listed in tools/list nor callable via tools/call. Unknown
    # levels and unset env fall back to "full" (all tools). The returned
    # count is what the HTTP /health route reports as the exposed tool count.
    exposed_tools = toolsets.configure_toolset(mcp)
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        transport = "streamable-http"
    elif transport == "streamable-http":
        pass
    else:
        transport = "stdio"

    if transport == "stdio":
        # transport is normalized to "stdio" above; pass the literal so mypy
        # sees the exact Literal type the MCP SDK's run() expects.
        mcp.run(transport="stdio")
        return

    # HTTP transport: build the Starlette app and wrap it with bearer auth
    # plus request logging (outermost, so every request incl. 401s is logged).
    # The /health route is added to the raw app FIRST (before auth/logging
    # wrap it) so it bypasses MCP_API_TOKEN — a healthcheck cannot carry the
    # token. stdio transport never builds this app.
    import uvicorn

    app = mcp.streamable_http_app()
    # Mount the unauthenticated /health route on the raw app BEFORE auth and
    # logging wrap it, so a healthcheck (which cannot carry MCP_API_TOKEN) is
    # answered before the bearer middleware sees the request.
    app.routes.extend(_health_app(exposed_tools).routes)
    token = os.environ.get("MCP_API_TOKEN", "").strip()
    app = _bearer_auth_middleware(app, token)
    app = _access_log_middleware(app)

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8081"))
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            # Keep our own logging config (NPG_LOG_LEVEL + timestamped format)
            # instead of uvicorn's dictConfig, which would replace it.
            log_config=None,
            # One access line per request is already emitted by
            # _access_log_middleware with tool name + timing — disable uvicorn's
            # duplicate access log so container logs stay readable.
            access_log=False,
        )
    )
    server.run()


if __name__ == "__main__":
    main()

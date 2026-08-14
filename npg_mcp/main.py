"""NginxProxyGuard MCP server — streamable-http transport."""

from __future__ import annotations

import hmac
import os
import warnings
from contextvars import ContextVar
from typing import Literal
from urllib.parse import quote

# Suppress MCP SDK v1.x pydantic-settings warning for unresolved forward
# reference in FastMCP.lifespan — harmless, fixed in MCP SDK 2.x
warnings.filterwarnings(
    "ignore",
    message=".*lifespan.*incomplete definition.*",
    category=UserWarning,
    module="pydantic_settings",
)

from mcp.server import transport_security
from mcp.server.fastmcp import FastMCP
import npg_mcp.client as client_mod

# Context variable for per-request token (future use)
_current_token: ContextVar[str] = ContextVar("npg_token", default="")


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
    """Get NPG client with auto-login from env credentials.

    Auth priority (highest first):
    1. NPG_API_TOKEN env var — long-lived API token (ng_... format).
       Immune to password changes; preferred for production.
    2. Per-request ContextVar token (set by MCP middleware).
    3. NPG_USERNAME/NPG_PASSWORD auto-login (JWT — invalidated on
       password change or session end).

    For JWT auth, a 401 on the first request triggers a single
    re-login attempt to recover from stale tokens.
    """
    # 1. Long-lived API token (preferred — survives password changes)
    api_token = os.environ.get("NPG_API_TOKEN", "").strip()
    if api_token:
        c = client_mod.NPGClient(token=api_token)
        # Some NPG endpoints (e.g. /status, /health/detailed) are JWT-only
        # and reject API tokens with 401. If username/password are also
        # available, transparently fall back to JWT for those endpoints.
        # The API token handles 95%+ of endpoints; JWT is a safety net.
        return c

    # 2. Per-request token from ContextVar
    token = client_mod.get_token()
    if token:
        c = client_mod.NPGClient(token=token)
        # If the JWT was invalidated (password change, session end),
        # re-authenticate once from env credentials.
        if os.environ.get("NPG_USERNAME") and os.environ.get("NPG_PASSWORD"):
            try:
                c.get("/api/v1/settings")
            except Exception:
                # Stale token — clear and re-login
                client_mod.set_token("")
                c.close()
                c = client_mod.NPGClient()
                c.login(
                    os.environ["NPG_USERNAME"],
                    os.environ["NPG_PASSWORD"],
                )
        return c

    # 3. Auto-login from env credentials
    username = os.environ.get("NPG_USERNAME", "")
    password = os.environ.get("NPG_PASSWORD", "")
    if username and password:
        c = client_mod.NPGClient()
        c.login(username, password)
        return c

    raise RuntimeError(
        "NPG_API_TOKEN or NPG_USERNAME/NPG_PASSWORD environment variables not set."
    )


def _get_jwt_client() -> client_mod.NPGClient:
    """Get a JWT-authenticated client (for JWT-only endpoints like /status).

    Some NPG endpoints reject API tokens and only accept session JWTs.
    This helper always logs in with username/password to get a fresh JWT.
    """
    username = os.environ.get("NPG_USERNAME", "")
    password = os.environ.get("NPG_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("NPG_USERNAME/NPG_PASSWORD required for JWT-only endpoints.")
    c = client_mod.NPGClient()
    c.login(username, password)
    return c


def _id_path(id_val) -> str:
    """Convert an ID (int or str) to a string for URL path interpolation."""
    return str(id_val)


# ── Proxy Hosts ───────────────────────────────────────────────────────

@mcp.tool(name="npg_list_proxy_hosts", description="List all proxy hosts. Returns a list of proxy host objects.")
async def npg_list_proxy_hosts() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/proxy-hosts")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host", description="Get a single proxy host by its ID. REQUIRED: host_id.")
async def npg_get_proxy_host(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_by_domain", description="Get a proxy host by its domain name.")
async def npg_get_proxy_host_by_domain(domain: str) -> dict:
    c = _get_client()
    try:
        encoded = quote(domain, safe="")
        data = c.get(f"/api/v1/proxy-hosts/by-domain/{encoded}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_proxy_host", description="Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: pass only the fields you want to change; omitted fields inherit global defaults or sensible built-in defaults. Fields: proxy_type (default 'http'), forward_scheme (default 'http'), enabled (default True), ssl_enabled, ssl_forced (default True), ssl_http2 (default True), ssl_http3, ssl_cert_id, waf_enabled, waf_use_global (default True), waf_paranoia_level, waf_anomaly_threshold, waf_mode, cache_enabled, cache_static_only, cache_ttl, cache_template, block_normal, block_http, block_exploits (default True), block_exploits_exceptions, allow_websocket_upgrade (default True), enable_proxy_headers, host_header, extra_domains, advanced_config, proxy_buffering (str), proxy_request_buffering (str), client_max_body_size (str), proxy_max_temp_file_size (str), proxy_connect/send/read_timeout, access_list_id, auth_provider_id, auth_bypass_paths, ddns_enabled/provider_id/proxied, forward_container_name/network, stream_* fields.")
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
    c = _get_client()
    try:
        body: dict = {}
        body["domain_names"] = domain_names
        body["forward_host"] = forward_host
        body["forward_port"] = forward_port
        if forward_scheme is not None: body["forward_scheme"] = forward_scheme
        if block_normal is not None: body["block_normal_access"] = block_normal
        if waf_enabled is not None: body["waf_enabled"] = waf_enabled
        if block_http is not None: body["block_http_requests"] = block_http
        if ssl_enabled is not None: body["ssl_enabled"] = ssl_enabled
        if ssl_forced is not None: body["ssl_force_https"] = ssl_forced
        if ssl_http2 is not None: body["ssl_http2"] = ssl_http2
        if ssl_http3 is not None: body["ssl_http3"] = ssl_http3
        if ssl_cert_id is not None: body["certificate_id"] = ssl_cert_id
        if cache_enabled is not None: body["cache_enabled"] = cache_enabled
        if cache_static_only is not None: body["cache_static_only"] = cache_static_only
        if cache_ttl is not None: body["cache_ttl"] = cache_ttl
        if cache_template is not None: body["cache_template"] = cache_template
        if advanced_config is not None: body["advanced_config"] = advanced_config
        if enable_proxy_headers is not None: body["enable_proxy_headers"] = enable_proxy_headers
        if host_header is not None: body["pass_host_header"] = host_header
        if extra_domains is not None: body["extra_domains"] = extra_domains
        if block_exploits is not None: body["block_exploits"] = block_exploits
        if block_exploits_exceptions is not None: body["block_exploits_exceptions"] = block_exploits_exceptions
        if allow_websocket_upgrade is not None: body["allow_websocket_upgrade"] = allow_websocket_upgrade
        if waf_use_global is not None: body["waf_use_global"] = waf_use_global
        if waf_paranoia_level is not None: body["waf_paranoia_level"] = waf_paranoia_level
        if waf_anomaly_threshold is not None: body["waf_anomaly_threshold"] = waf_anomaly_threshold
        if waf_mode is not None: body["waf_mode"] = waf_mode
        if proxy_connect_timeout is not None: body["proxy_connect_timeout"] = proxy_connect_timeout
        if proxy_send_timeout is not None: body["proxy_send_timeout"] = proxy_send_timeout
        if proxy_read_timeout is not None: body["proxy_read_timeout"] = proxy_read_timeout
        if proxy_buffering is not None: body["proxy_buffering"] = proxy_buffering
        if proxy_request_buffering is not None: body["proxy_request_buffering"] = proxy_request_buffering
        if client_max_body_size is not None: body["client_max_body_size"] = client_max_body_size
        if proxy_max_temp_file_size is not None: body["proxy_max_temp_file_size"] = proxy_max_temp_file_size
        if access_list_id is not None: body["access_list_id"] = _id_path(access_list_id)
        if auth_provider_id is not None: body["auth_provider_id"] = _id_path(auth_provider_id)
        if auth_bypass_paths is not None: body["auth_bypass_paths"] = auth_bypass_paths
        if ddns_enabled is not None: body["ddns_enabled"] = ddns_enabled
        if ddns_provider_id is not None: body["ddns_provider_id"] = _id_path(ddns_provider_id)
        if ddns_proxied is not None: body["ddns_proxied"] = ddns_proxied
        if forward_container_name is not None: body["forward_container_name"] = forward_container_name
        if forward_container_network is not None: body["forward_container_network"] = forward_container_network
        body["proxy_type"] = proxy_type
        body["enabled"] = enabled
        if stream_listen_host is not None: body["stream_listen_host"] = stream_listen_host
        if stream_listen_port is not None: body["stream_listen_port"] = stream_listen_port
        if stream_protocol is not None: body["stream_protocol"] = stream_protocol
        if stream_ssl_preread is not None: body["stream_ssl_preread"] = stream_ssl_preread
        if stream_accept_proxy_protocol is not None: body["stream_accept_proxy_protocol"] = stream_accept_proxy_protocol
        if stream_send_proxy_protocol is not None: body["stream_send_proxy_protocol"] = stream_send_proxy_protocol
        if stream_proxy_connect_timeout is not None: body["stream_proxy_connect_timeout"] = stream_proxy_connect_timeout
        if stream_proxy_timeout is not None: body["stream_proxy_timeout"] = stream_proxy_timeout

        data = c.post("/api/v1/proxy-hosts", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host", description="Update an existing proxy host (partial update — pass only the fields you want to change; omitted fields are left as-is). Use `skip_nginx=true` to skip nginx regeneration. Fields: domain_names, forward_host, forward_port, forward_scheme, block_normal, waf_enabled, waf_use_global (bool | None — tri-state: omit=leave unchanged, false=host own WAF config, true=inherit global WAF), waf_paranoia_level, waf_anomaly_threshold, block_http, ssl_forced, ssl_cert_id, cache_enabled, cache_static_only, cache_ttl (str), cache_template, advanced_config, enable_proxy_headers, host_header, extra_domains, enabled, ssl_http2, ssl_http3, block_exploits, block_exploits_exceptions, allow_websocket_upgrade, proxy_connect/send/read_timeout, proxy_buffering (str: 'on'/'off'/''), proxy_request_buffering (str: 'on'/'off'/''), client_max_body_size (str, e.g. '10m'/'off'), proxy_max_temp_file_size (str), access_list_id, auth_provider_id, auth_bypass_paths (list[str]), ddns_enabled/provider_id/proxied, forward_container_name/network. Nullable id fields (certificate_id, access_list_id, auth_provider_id, ddns_provider_id, forward_container_name/network): empty string clears, omitted leaves unchanged; auth_bypass_paths: [] clears. REQUIRED: host_id.")
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
    c = _get_client()
    try:
        body: dict = {}
        if domain_names is not None: body["domain_names"] = domain_names
        if forward_host is not None: body["forward_host"] = forward_host
        if forward_port is not None: body["forward_port"] = forward_port
        if forward_scheme is not None: body["forward_scheme"] = forward_scheme
        if block_normal is not None: body["block_normal_access"] = block_normal
        if waf_enabled is not None: body["waf_enabled"] = waf_enabled
        if waf_use_global is not None: body["waf_use_global"] = waf_use_global
        if waf_paranoia_level is not None: body["waf_paranoia_level"] = waf_paranoia_level
        if waf_anomaly_threshold is not None: body["waf_anomaly_threshold"] = waf_anomaly_threshold
        if block_http is not None: body["block_http_requests"] = block_http
        if ssl_forced is not None: body["ssl_force_https"] = ssl_forced
        if ssl_cert_id is not None: body["certificate_id"] = ssl_cert_id
        if cache_enabled is not None: body["cache_enabled"] = cache_enabled
        if cache_static_only is not None: body["cache_static_only"] = cache_static_only
        if cache_ttl is not None: body["cache_ttl"] = cache_ttl
        if cache_template is not None: body["cache_template"] = cache_template
        if advanced_config is not None: body["advanced_config"] = advanced_config
        if enable_proxy_headers is not None: body["enable_proxy_headers"] = enable_proxy_headers
        if host_header is not None: body["pass_host_header"] = host_header
        if extra_domains is not None: body["extra_domains"] = extra_domains
        if enabled is not None: body["enabled"] = enabled
        if ssl_http2 is not None: body["ssl_http2"] = ssl_http2
        if ssl_http3 is not None: body["ssl_http3"] = ssl_http3
        if block_exploits is not None: body["block_exploits"] = block_exploits
        if block_exploits_exceptions is not None: body["block_exploits_exceptions"] = block_exploits_exceptions
        if allow_websocket_upgrade is not None: body["allow_websocket_upgrade"] = allow_websocket_upgrade
        if proxy_connect_timeout is not None: body["proxy_connect_timeout"] = proxy_connect_timeout
        if proxy_send_timeout is not None: body["proxy_send_timeout"] = proxy_send_timeout
        if proxy_read_timeout is not None: body["proxy_read_timeout"] = proxy_read_timeout
        if proxy_buffering is not None: body["proxy_buffering"] = proxy_buffering
        if proxy_request_buffering is not None: body["proxy_request_buffering"] = proxy_request_buffering
        if client_max_body_size is not None: body["client_max_body_size"] = client_max_body_size
        if proxy_max_temp_file_size is not None: body["proxy_max_temp_file_size"] = proxy_max_temp_file_size
        if access_list_id is not None: body["access_list_id"] = _id_path(access_list_id)
        if auth_provider_id is not None: body["auth_provider_id"] = _id_path(auth_provider_id)
        if auth_bypass_paths is not None: body["auth_bypass_paths"] = auth_bypass_paths
        if ddns_enabled is not None: body["ddns_enabled"] = ddns_enabled
        if ddns_provider_id is not None: body["ddns_provider_id"] = _id_path(ddns_provider_id)
        if ddns_proxied is not None: body["ddns_proxied"] = ddns_proxied
        if forward_container_name is not None: body["forward_container_name"] = forward_container_name
        if forward_container_network is not None: body["forward_container_network"] = forward_container_network

        params = {"skip_nginx": "true"} if skip_nginx else None
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}", body, params=params)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host", description="Delete a proxy host by its ID. REQUIRED: host_id.")
async def npg_delete_proxy_host(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}")
        return {"success": True, "message": f"Proxy host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_proxy_host", description="Test upstream connectivity for a proxy host. REQUIRED: host_id.")
async def npg_test_proxy_host(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/test")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_regenerate_config", description="Regenerate nginx config for a specific proxy host without touching others. REQUIRED: host_id.")
async def npg_regenerate_config(host_id: str | int) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/clone", {"domain_names": domain_names})
        return {"success": True, "data": data}
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
    c = _get_client()
    try:
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
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        c.delete(f"/api/v1/certificates/{_id_path(cert_id)}")
        return {"success": True, "message": f"Certificate {_id_path(cert_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_renew_certificate", description="Renew a certificate by its ID. REQUIRED: cert_id.")
async def npg_renew_certificate(cert_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/certificates/{_id_path(cert_id)}/renew")
        return {"success": True, "data": data}
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

@mcp.tool(name="npg_test_nginx", description="Test nginx configuration for validity.")
async def npg_test_nginx() -> dict:
    """Test nginx configuration for validity."""
    c = _get_client()
    try:
        data = c.post("/api/v1/proxy-hosts/sync")
        return {"success": True, "data": {"test_success": data.get("test_success", True), "reload_success": data.get("reload_success", True)}}
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/redirect-hosts/{_id_path(host_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_redirect_host", description="Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, default 301).")
async def npg_create_redirect_host(
    domain_names: list[str],
    forward_domain_name: str,
    forward_scheme: str = "auto",
    preserve_path: bool = True,
    redirect_code: Literal[301, 302, 303, 307, 308] = 301,
) -> dict:
    c = _get_client()
    try:
        body = {
            "domain_names": domain_names,
            "forward_domain_name": forward_domain_name,
            "forward_scheme": forward_scheme,
            "preserve_path": preserve_path,
            "redirect_code": redirect_code,
        }
        data = c.post("/api/v1/redirect-hosts", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_redirect_host", description="Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code. REQUIRED: host_id.")
async def npg_update_redirect_host(
    host_id: str | int,
    domain_names: list[str] | None = None,
    forward_domain_name: str | None = None,
    forward_scheme: str | None = None,
    preserve_path: bool | None = None,
    redirect_code: int | None = None,
) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if domain_names is not None: body["domain_names"] = domain_names
        if forward_domain_name is not None: body["forward_domain_name"] = forward_domain_name
        if forward_scheme is not None: body["forward_scheme"] = forward_scheme
        if preserve_path is not None: body["preserve_path"] = preserve_path
        if redirect_code is not None: body["redirect_code"] = redirect_code
        data = c.put(f"/api/v1/redirect-hosts/{_id_path(host_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_redirect_host", description="Delete a redirect host by its ID. REQUIRED: host_id.")
async def npg_delete_redirect_host(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/redirect-hosts/{_id_path(host_id)}")
        return {"success": True, "message": f"Redirect host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Security Features (per proxy host) ────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_rate_limit", description="GET rate limit configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_rate_limit(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_rate_limit", description="UPDATE rate limit configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), requests_per_second (int), burst_size (int), zone_size (str), limit_by (str: ip/uri/ip_uri), limit_response (int), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global) REQUIRED: host_id.")
async def npg_update_proxy_host_rate_limit(host_id: str | int, enabled: bool | None = None, requests_per_second: int | None = None, burst_size: int | None = None, zone_size: str | None = None, limit_by: str | None = None, limit_response: int | None = None, disable_global: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if requests_per_second is not None: body["requests_per_second"] = requests_per_second
        if burst_size is not None: body["burst_size"] = burst_size
        if zone_size is not None: body["zone_size"] = zone_size
        if limit_by is not None: body["limit_by"] = limit_by
        if limit_response is not None: body["limit_response"] = limit_response
        if disable_global is not None: body["disable_global"] = disable_global
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_bot_filter", description="GET bot filter configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_bot_filter(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_bot_filter", description="UPDATE bot filter configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Required: host_id (str|int). Optional: enabled (bool), block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), custom_blocked_agents (str, comma-separated list), custom_allowed_agents (str, comma-separated list).")
async def npg_update_proxy_host_bot_filter(host_id: str | int, enabled: bool | None = None, block_bad_bots: bool | None = None, block_ai_bots: bool | None = None, allow_search_engines: bool | None = None, block_suspicious_clients: bool | None = None, challenge_suspicious: bool | None = None, disable_global: bool | None = None, custom_blocked_agents: str | None = None, custom_allowed_agents: str | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if block_bad_bots is not None: body["block_bad_bots"] = block_bad_bots
        if block_ai_bots is not None: body["block_ai_bots"] = block_ai_bots
        if allow_search_engines is not None: body["allow_search_engines"] = allow_search_engines
        if block_suspicious_clients is not None: body["block_suspicious_clients"] = block_suspicious_clients
        if challenge_suspicious is not None: body["challenge_suspicious"] = challenge_suspicious
        if disable_global is not None: body["disable_global"] = disable_global
        if custom_blocked_agents is not None:
            body["custom_blocked_agents"] = custom_blocked_agents
        if custom_allowed_agents is not None:
            body["custom_allowed_agents"] = custom_allowed_agents
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_security_headers", description="GET security headers configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_security_headers(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_security_headers", description="UPDATE security headers for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), hsts_enabled (bool), hsts_max_age (int), hsts_include_subdomains (bool), hsts_preload (bool), x_frame_options (str: DENY/SAMEORIGIN/''), x_content_type_options (bool), x_xss_protection (bool), referrer_policy (str), content_security_policy (str), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global) REQUIRED: host_id.")
async def npg_update_proxy_host_security_headers(host_id: str | int, enabled: bool | None = None, hsts_enabled: bool | None = None, hsts_max_age: int | None = None, hsts_include_subdomains: bool | None = None, hsts_preload: bool | None = None, x_frame_options: str | None = None, x_content_type_options: bool | None = None, x_xss_protection: bool | None = None, referrer_policy: str | None = None, content_security_policy: str | None = None, disable_global: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if hsts_enabled is not None: body["hsts_enabled"] = hsts_enabled
        if hsts_max_age is not None: body["hsts_max_age"] = hsts_max_age
        if hsts_include_subdomains is not None: body["hsts_include_subdomains"] = hsts_include_subdomains
        if hsts_preload is not None: body["hsts_preload"] = hsts_preload
        if x_frame_options is not None: body["x_frame_options"] = x_frame_options
        if x_content_type_options is not None: body["x_content_type_options"] = x_content_type_options
        if x_xss_protection is not None: body["x_xss_protection"] = x_xss_protection
        if referrer_policy is not None: body["referrer_policy"] = referrer_policy
        if content_security_policy is not None: body["content_security_policy"] = content_security_policy
        if disable_global is not None: body["disable_global"] = disable_global
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_apply_security_header_preset", description="APPLY a security header preset to a proxy host. preset: strict, balanced, or relaxed. REQUIRED: host_id.")
async def npg_apply_security_header_preset(host_id: str | int, preset: Literal["strict", "balanced", "relaxed"]) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers/preset/{preset}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_upstream", description="GET upstream/load balancing configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_upstream(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_upstream", description="UPDATE upstream/load balancing configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: scheme, servers (list of {address, port, weight, backup}), load_balance, health_check_enabled, health_check_path, health_check_interval. REQUIRED: host_id.")
async def npg_update_proxy_host_upstream(host_id: str | int, scheme: str | None = None, servers: list[dict] | None = None, load_balance: str | None = None, health_check_enabled: bool | None = None, health_check_path: str | None = None, health_check_interval: int | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if scheme is not None: body["scheme"] = scheme
        if servers is not None: body["servers"] = servers
        if load_balance is not None: body["load_balance"] = load_balance
        if health_check_enabled is not None: body["health_check_enabled"] = health_check_enabled
        if health_check_path is not None: body["health_check_path"] = health_check_path
        if health_check_interval is not None: body["health_check_interval"] = health_check_interval
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_uri_block", description="GET URI block configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_uri_block(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_uri_block", description="UPDATE URI block configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips. REQUIRED: host_id.")
async def npg_update_proxy_host_uri_block(host_id: str | int, enabled: bool | None = None, rules: list[dict] | None = None, exception_ips: list[str] | None = None, allow_private_ips: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if rules is not None: body["rules"] = rules
        if exception_ips is not None: body["exception_ips"] = exception_ips
        if allow_private_ips is not None: body["allow_private_ips"] = allow_private_ips
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/access-lists/{_id_path(list_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_access_list", description="Create a new access list. Required: name, advanced_config (block/allow rules).")
async def npg_create_access_list(name: str, advanced_config: str = "", clients: list | None = None) -> dict:
    c = _get_client()
    try:
        body = {
            "name": name,
            "advanced_config": advanced_config,
            "clients": clients or [],
        }
        data = c.post("/api/v1/access-lists", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_access_list", description="Update an access list. Pass only fields to change. REQUIRED: list_id.")
async def npg_update_access_list(list_id: str | int, name: str | None = None, advanced_config: str | None = None, clients: list | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if name is not None: body["name"] = name
        if advanced_config is not None: body["advanced_config"] = advanced_config
        if clients is not None: body["clients"] = clients
        data = c.put(f"/api/v1/access-lists/{_id_path(list_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_access_list", description="Delete an access list by its ID. REQUIRED: list_id.")
async def npg_delete_access_list(list_id: str | int) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/dns-providers/{_id_path(provider_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_dns_provider", description="Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}).")
async def npg_create_dns_provider(name: str, provider_type: str, credentials: dict | None = None, kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        body = {"name": name, "provider_type": provider_type}
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
    c = _get_client()
    try:
        data = c.put(f"/api/v1/dns-providers/{_id_path(provider_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_dns_provider", description="Delete a DNS provider by its ID. REQUIRED: provider_id.")
async def npg_delete_dns_provider(provider_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/dns-providers/{_id_path(provider_id)}")
        return {"success": True, "message": f"DNS provider {_id_path(provider_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_dns_provider", description="Test DNS provider credentials. REQUIRED: provider_id.")
async def npg_test_dns_provider(provider_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/dns-providers/test", {"dns_provider_id": provider_id})
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/cloud-providers/{slug}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_cloud_provider", description="Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description.")
async def npg_create_cloud_provider(name: str, slug: str, ip_ranges: list[str], region: str | None = None, description: str | None = None, kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.put(f"/api/v1/cloud-providers/{slug}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_cloud_provider", description="Delete a cloud provider by its slug.")
async def npg_delete_cloud_provider(slug: str) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/cloud-providers/{slug}")
        return {"success": True, "message": f"Cloud provider {slug} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_cloud_blocking", description="GET per-host cloud provider blocking configuration. Returns blocked_providers, challenge_mode, allow_search_bots, cloud_disable_global. REQUIRED: host_id.")
async def npg_get_proxy_host_cloud_blocking(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/blocked-cloud-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_cloud_blocking", description="UPDATE per-host cloud provider blocking (the endpoint full-replaces all fields, so the tool reads current settings and merges — omitted fields are left as-is). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool), cloud_disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global). REQUIRED: host_id.")
async def npg_update_proxy_host_cloud_blocking(host_id: str | int, blocked_providers: list[str] | None = None, challenge_mode: bool | None = None, allow_search_bots: bool | None = None, cloud_disable_global: bool | None = None) -> dict:
    c = _get_client()
    try:
        # Read-modify-write: upstream SetBlockedProviders full-replaces all 4 fields.
        current = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/blocked-cloud-providers")
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_proxy_host_geo", description="CREATE geo restriction for a proxy host. Required: host_id, countries (list of ISO codes, min 1). Optional: mode (whitelist/blacklist, default blacklist), allowed_ips, challenge_mode, disable_global (bool — false=inherit, true=disable global), allow_private_ips, allow_search_bots")
async def npg_create_proxy_host_geo(host_id: str | int, countries: list[str], mode: Literal["whitelist", "blacklist"] = "blacklist", enabled: bool = True, allowed_ips: list[str] | None = None, challenge_mode: bool = False, disable_global: bool = False, allow_private_ips: bool = True, allow_search_bots: bool = True) -> dict:
    c = _get_client()
    try:
        body: dict = {"mode": mode, "countries": countries, "enabled": enabled, "challenge_mode": challenge_mode, "disable_global": disable_global, "allow_private_ips": allow_private_ips, "allow_search_bots": allow_search_bots}
        if allowed_ips is not None: body["allowed_ips"] = allowed_ips
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_geo", description="UPDATE geo restriction for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode, disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), allow_private_ips, allow_search_bots REQUIRED: host_id.")
async def npg_update_proxy_host_geo(host_id: str | int, enabled: bool | None = None, mode: Literal["whitelist", "blacklist"] | None = None, countries: list[str] | None = None, allowed_ips: list[str] | None = None, challenge_mode: bool | None = None, disable_global: bool | None = None, allow_private_ips: bool | None = None, allow_search_bots: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if mode is not None: body["mode"] = mode
        if countries is not None: body["countries"] = countries
        if allowed_ips is not None: body["allowed_ips"] = allowed_ips
        if challenge_mode is not None: body["challenge_mode"] = challenge_mode
        if disable_global is not None: body["disable_global"] = disable_global
        if allow_private_ips is not None: body["allow_private_ips"] = allow_private_ips
        if allow_search_bots is not None: body["allow_search_bots"] = allow_search_bots
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_geo", description="DELETE geo restriction for a proxy host. REQUIRED: host_id.")
async def npg_delete_proxy_host_geo(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo")
        return {"success": True, "message": f"Geo restriction for host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Fail2ban (per proxy host) ─────────────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_fail2ban", description="GET fail2ban configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_fail2ban(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_fail2ban", description="UPDATE fail2ban configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge). REQUIRED: host_id.")
async def npg_update_proxy_host_fail2ban(host_id: str | int, enabled: bool | None = None, max_retries: int | None = None, find_time: int | None = None, ban_time: int | None = None, fail_codes: str | None = None, action: Literal["block", "challenge"] | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if max_retries is not None: body["max_retries"] = max_retries
        if find_time is not None: body["find_time"] = find_time
        if ban_time is not None: body["ban_time"] = ban_time
        if fail_codes is not None: body["fail_codes"] = fail_codes
        if action is not None: body["action"] = action
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Challenge/CAPTCHA (per proxy host) ────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_challenge", description="GET CAPTCHA/challenge configuration for a proxy host. REQUIRED: host_id.")
async def npg_get_proxy_host_challenge(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_challenge", description="UPDATE CAPTCHA/challenge configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), challenge_type (str), site_key (str), token_validity (int), min_score (float), apply_to (str), page_title (str) REQUIRED: host_id.")
async def npg_update_proxy_host_challenge(host_id: str | int, enabled: bool | None = None, challenge_type: str | None = None, site_key: str | None = None, token_validity: int | None = None, min_score: float | None = None, apply_to: str | None = None, page_title: str | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if challenge_type is not None: body["challenge_type"] = challenge_type
        if site_key is not None: body["site_key"] = site_key
        if token_validity is not None: body["token_validity"] = token_validity
        if min_score is not None: body["min_score"] = min_score
        if apply_to is not None: body["apply_to"] = apply_to
        if page_title is not None: body["page_title"] = page_title
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_challenge", description="DELETE CAPTCHA/challenge configuration for a proxy host. REQUIRED: host_id.")
async def npg_delete_proxy_host_challenge(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge")
        return {"success": True, "message": f"Challenge configuration for host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_verify_challenge", description="Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution.")
async def npg_verify_challenge(token: str, solution: str) -> dict:
    c = _get_client()
    try:
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

@mcp.tool(name="npg_ban_ip", description="Ban an IP address. REQUIRED: ip_address. Optional: ban_time (seconds).")
async def npg_ban_ip(ip_address: str, reason: str = "Manual ban via API", duration: int = 3600) -> dict:
    """Ban an IP address. Required: ip_address. Optional: reason, duration (seconds, 0=permanent)."""
    c = _get_client()
    try:
        data = c.post("/api/v1/banned-ips", {"ip_address": ip_address, "reason": reason, "duration": duration})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_unban_ip", description="Unban an IP by its ID. REQUIRED: ip_id.")
async def npg_unban_ip(ip_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/banned-ips/{_id_path(ip_id)}")
        return {"success": True, "message": f"IP ban {_id_path(ip_id)} removed"}
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/exploit-rules/{_id_path(rule_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_exploit_rule", description="Create an exploit block rule. Required: category, name, pattern, pattern_type (e.g. 'query_string'). Optional: severity, description.")
async def npg_create_exploit_rule(category: str, name: str, pattern: str, pattern_type: str, severity: str | None = None, description: str | None = None, kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.put(f"/api/v1/exploit-rules/{_id_path(rule_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_exploit_rule", description="Delete an exploit rule by its ID. REQUIRED: rule_id.")
async def npg_delete_exploit_rule(rule_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/exploit-rules/{_id_path(rule_id)}")
        return {"success": True, "message": f"Exploit rule {_id_path(rule_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_toggle_exploit_rule", description="Toggle an exploit rule's enabled status. REQUIRED: rule_id.")
async def npg_toggle_exploit_rule(rule_id: str | int) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/waf/hosts/{_id_path(host_id)}/config")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_disable_waf_rule", description="Disable a WAF rule for a specific proxy host. REQUIRED: host_id, rule_id.")
async def npg_disable_waf_rule(host_id: str | int, rule_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/waf/hosts/{_id_path(host_id)}/rules/{_id_path(rule_id)}/disable")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Logs ──────────────────────────────────────────────────────────────

@mcp.tool(name="npg_get_logs", description="Get access logs.")
async def npg_get_logs() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/logs")
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

@mcp.tool(name="npg_list_audit_logs", description="List audit log entries.")
async def npg_list_audit_logs() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/audit-logs")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_list_system_logs", description="List system logs.")
async def npg_list_system_logs() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-logs")
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
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        c.delete(f"/api/v1/backups/{_id_path(backup_id)}")
        return {"success": True, "message": f"Backup {_id_path(backup_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_restore_backup", description="Restore from a backup. Required: backup_id.")
async def npg_restore_backup(backup_id: str | int) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/api-tokens/{_id_path(token_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_api_token", description="Create a new API token. Required: name, permissions (array). Optional: expires_at.")
async def npg_create_api_token(name: str, permissions: list[str], expires_at: str | None = None) -> dict:
    c = _get_client()
    try:
        body = {"name": name, "permissions": permissions, "expires_at": expires_at}
        data = c.post("/api/v1/api-tokens", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_api_token", description="Update an API token. Pass only fields to change (dict). REQUIRED: token_id.")
async def npg_update_api_token(token_id: str | int, kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/api-tokens/{_id_path(token_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_revoke_api_token", description="Revoke an API token by its ID. REQUIRED: token_id.")
async def npg_revoke_api_token(token_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/api-tokens/{_id_path(token_id)}/revoke")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_api_token", description="Delete an API token by its ID. REQUIRED: token_id.")
async def npg_delete_api_token(token_id: str | int) -> dict:
    c = _get_client()
    try:
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

@mcp.tool(name="npg_create_notification_channel", description="Create a notification channel. REQUIRED: name, channel_type ('webhook'/'discord'/'telegram'). Optional: config (dict, e.g. {'url': '...'} for webhook/discord, {'bot_token': '...', 'chat_id': '...'} for telegram), events (list of event keys, e.g. ['ip.banned', 'cert.renewal_failed'] — at least one event or digest_enabled required), allow_private_target (bool, allow private-network webhook URLs), digest_enabled (bool), digest_hour (int 0-23).")
async def npg_create_notification_channel(name: str, channel_type: str, config: dict | None = None, events: list[str] | None = None, allow_private_target: bool = False, digest_enabled: bool = False, digest_hour: int = 9) -> dict:
    c = _get_client()
    try:
        body = {"name": name, "type": channel_type, "allow_private_target": allow_private_target, "digest_enabled": digest_enabled, "digest_hour": digest_hour}
        if config:
            body["config"] = config
        if events:
            body["events"] = events
        data = c.post("/api/v1/notification-channels", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_notification_channel", description="Update a notification channel. Pass only fields to change. REQUIRED: channel_id.")
async def npg_update_notification_channel(channel_id: str | int, name: str | None = None, channel_type: str | None = None, config: dict | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if name is not None: body["name"] = name
        if channel_type is not None: body["type"] = channel_type
        if config is not None: body["config"] = config
        data = c.put(f"/api/v1/notification-channels/{_id_path(channel_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_notification_channel", description="Delete a notification channel by its ID. REQUIRED: channel_id.")
async def npg_delete_notification_channel(channel_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/notification-channels/{_id_path(channel_id)}")
        return {"success": True, "message": f"Notification channel {_id_path(channel_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_notification_channel", description="Test a notification channel by sending a test message. REQUIRED: channel_id.")
async def npg_test_notification_channel(channel_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/notification-channels/{_id_path(channel_id)}/test")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_notification_deliveries", description="Get delivery history for a notification channel. REQUIRED: channel_id.")
async def npg_get_notification_deliveries(channel_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/notification-channels/{_id_path(channel_id)}/deliveries")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_detect_telegram_chats", description="Detect available Telegram chats for notification delivery.")
async def npg_detect_telegram_chats() -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/notification-channels/detect-telegram-chats")
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/users/{_id_path(user_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_user", description="Create a new user. Required: username, email, password. Optional: role_id, is_active.")
async def npg_create_user(username: str, email: str, password: str, role_id: str | int | None = None, is_active: bool = True) -> dict:
    c = _get_client()
    try:
        body = {"username": username, "email": email, "password": password, "is_active": is_active}
        if role_id is not None:
            body["role_id"] = _id_path(role_id)
        data = c.post("/api/v1/users", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_set_user_password", description="Set/reset a user's password. Required: user_id, new_password.")
async def npg_set_user_password(user_id: str | int, new_password: str) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/users/{_id_path(user_id)}/password", {"password": new_password})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_end_user_sessions", description="End all sessions for a user (force logout). Required: user_id.")
async def npg_end_user_sessions(user_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/users/{_id_path(user_id)}/end-sessions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_user", description="Delete a user by their ID. REQUIRED: user_id.")
async def npg_delete_user(user_id: str | int) -> dict:
    c = _get_client()
    try:
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

@mcp.tool(name="npg_create_role", description="Create a new role. Required: name, permissions (array of permission strings).")
async def npg_create_role(name: str, permissions: list[str]) -> dict:
    c = _get_client()
    try:
        body = {"name": name, "permissions": permissions}
        data = c.post("/api/v1/roles", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_role", description="Update a role. Pass only fields to change. REQUIRED: role_id.")
async def npg_update_role(role_id: str | int, name: str | None = None, permissions: list[str] | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if name is not None: body["name"] = name
        if permissions is not None: body["permissions"] = permissions
        data = c.put(f"/api/v1/roles/{_id_path(role_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_role", description="Delete a role by its ID. REQUIRED: role_id.")
async def npg_delete_role(role_id: str | int) -> dict:
    c = _get_client()
    try:
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

@mcp.tool(name="npg_create_sso_provider", description="Create a new SSO provider. Required: slug, name, issuer_url, client_id. Optional: client_secret (defaults to placeholder), scopes.")
async def npg_create_sso_provider(slug: str, name: str, issuer_url: str, client_id: str, client_secret: str | None = None, scopes: str | None = None) -> dict:
    c = _get_client()
    try:
        body = {"slug": slug, "name": name, "issuer_url": issuer_url, "client_id": client_id}
        if client_secret is not None:
            body["client_secret"] = client_secret
        if scopes is not None:
            body["scopes"] = scopes
        data = c.post("/api/v1/sso-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_sso_provider", description="Update an SSO provider. Pass only fields to change. Required: provider_id. Optional: name, slug, issuer_url, client_id, client_secret (send '********' to leave unchanged), scopes.")
async def npg_update_sso_provider(provider_id: str | int, name: str | None = None, slug: str | None = None, issuer_url: str | None = None, client_id: str | None = None, client_secret: str | None = None, scopes: str | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if name is not None: body["name"] = name
        if slug is not None: body["slug"] = slug
        if issuer_url is not None: body["issuer_url"] = issuer_url
        if client_id is not None: body["client_id"] = client_id
        if client_secret is not None: body["client_secret"] = client_secret
        if scopes is not None: body["scopes"] = scopes
        data = c.put(f"/api/v1/sso-providers/{_id_path(provider_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_sso_provider", description="Delete an SSO provider by its ID. REQUIRED: provider_id.")
async def npg_delete_sso_provider(provider_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/sso-providers/{_id_path(provider_id)}")
        return {"success": True, "message": f"SSO provider {_id_path(provider_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_sso_provider", description="Test SSO provider configuration by initiating a test login flow. REQUIRED: provider_id.")
async def npg_test_sso_provider(provider_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/sso-providers/{_id_path(provider_id)}/test")
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
    c = _get_client()
    try:
        encoded = quote(filename, safe="")
        data = c.get_text(f"/api/v1/system-settings/log-files/{encoded}/download")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_view_log_file", description="View the contents of a log file. REQUIRED: filename.")
async def npg_view_log_file(filename: str, lines: int = 100) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
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
    c = _get_client()
    try:
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
    c = _get_client()
    try:
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
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if rules is not None: body["rules"] = rules
        if exception_ips is not None: body["exception_ips"] = exception_ips
        if allow_private_ips is not None: body["allow_private_ips"] = allow_private_ips
        data = c.put("/api/v1/global-uri-block", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_global_uri_block_rule", description="Add a rule to the global URI block. Required: pattern, action. Optional: is_regex.")
async def npg_add_global_uri_block_rule(pattern: str, action: str = "block", is_regex: bool = False) -> dict:
    c = _get_client()
    try:
        body = {"pattern": pattern, "action": action, "is_regex": is_regex}
        data = c.post("/api/v1/global-uri-block/rules", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_global_uri_block_rule", description="Delete a rule from the global URI block by its ID. REQUIRED: rule_id.")
async def npg_delete_global_uri_block_rule(rule_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/global-uri-block/rules/{_id_path(rule_id)}")
        return {"success": True, "message": f"Global URI block rule {_id_path(rule_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Upstream Health ────────────────────────────────────────────────────

@mcp.tool(name="npg_get_upstream_health", description="GET health status of an upstream pool. REQUIRED: upstream_id (UUID string).")
async def npg_get_upstream_health(upstream_id: str) -> dict:
    c = _get_client()
    try:
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

@mcp.tool(name="npg_update_global_security_headers", description="UPDATE global security headers configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options, x_content_type_options, x_xss_protection, referrer_policy, content_security_policy.")
async def npg_update_global_security_headers(enabled: bool | None = None, hsts_enabled: bool | None = None, hsts_max_age: int | None = None, hsts_include_subdomains: bool | None = None, hsts_preload: bool | None = None, x_frame_options: str | None = None, x_content_type_options: bool | None = None, x_xss_protection: bool | None = None, referrer_policy: str | None = None, content_security_policy: str | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if hsts_enabled is not None: body["hsts_enabled"] = hsts_enabled
        if hsts_max_age is not None: body["hsts_max_age"] = hsts_max_age
        if hsts_include_subdomains is not None: body["hsts_include_subdomains"] = hsts_include_subdomains
        if hsts_preload is not None: body["hsts_preload"] = hsts_preload
        if x_frame_options is not None: body["x_frame_options"] = x_frame_options
        if x_content_type_options is not None: body["x_content_type_options"] = x_content_type_options
        if x_xss_protection is not None: body["x_xss_protection"] = x_xss_protection
        if referrer_policy is not None: body["referrer_policy"] = referrer_policy
        if content_security_policy is not None: body["content_security_policy"] = content_security_policy
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
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if block_bad_bots is not None: body["block_bad_bots"] = block_bad_bots
        if block_ai_bots is not None: body["block_ai_bots"] = block_ai_bots
        if allow_search_engines is not None: body["allow_search_engines"] = allow_search_engines
        if block_suspicious_clients is not None: body["block_suspicious_clients"] = block_suspicious_clients
        if challenge_suspicious is not None: body["challenge_suspicious"] = challenge_suspicious
        if custom_blocked_agents is not None: body["custom_blocked_agents"] = custom_blocked_agents
        if custom_allowed_agents is not None: body["custom_allowed_agents"] = custom_allowed_agents
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
        body: dict = {}
        if blocked_providers is not None: body["blocked_providers"] = blocked_providers
        if challenge_mode is not None: body["challenge_mode"] = challenge_mode
        if allow_search_bots is not None: body["allow_search_bots"] = allow_search_bots
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

@mcp.tool(name="npg_update_global_geo", description="UPDATE global GeoIP restriction configuration (partial update — only provided fields are changed; omitted fields are left as-is. The global default is inherited by hosts without their own override). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, allow_private_ips, allow_search_bots, challenge_mode")
async def npg_update_global_geo(enabled: bool | None = None, mode: Literal["whitelist", "blacklist"] | None = None, countries: list[str] | None = None, allowed_ips: list[str] | None = None, allow_private_ips: bool | None = None, allow_search_bots: bool | None = None, challenge_mode: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if mode is not None: body["mode"] = mode
        if countries is not None: body["countries"] = countries
        if allowed_ips is not None: body["allowed_ips"] = allowed_ips
        if allow_private_ips is not None: body["allow_private_ips"] = allow_private_ips
        if allow_search_bots is not None: body["allow_search_bots"] = allow_search_bots
        if challenge_mode is not None: body["challenge_mode"] = challenge_mode
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

@mcp.tool(name="npg_update_global_rate_limit", description="UPDATE global rate limit configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, requests_per_second, burst_size, zone_size, limit_by, limit_response.")
async def npg_update_global_rate_limit(enabled: bool | None = None, requests_per_second: int | None = None, burst_size: int | None = None, zone_size: str | None = None, limit_by: str | None = None, limit_response: int | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if requests_per_second is not None: body["requests_per_second"] = requests_per_second
        if burst_size is not None: body["burst_size"] = burst_size
        if zone_size is not None: body["zone_size"] = zone_size
        if limit_by is not None: body["limit_by"] = limit_by
        if limit_response is not None: body["limit_response"] = limit_response
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

@mcp.tool(name="npg_update_global_waf", description="UPDATE global WAF configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, paranoia_level, anomaly_threshold, rules (list of {id, enabled}).")
async def npg_update_global_waf(enabled: bool | None = None, paranoia_level: int | None = None, anomaly_threshold: int | None = None, rules: list[dict] | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if paranoia_level is not None: body["paranoia_level"] = paranoia_level
        if anomaly_threshold is not None: body["anomaly_threshold"] = anomaly_threshold
        if rules is not None: body["rules"] = rules
        data = c.put("/api/v1/settings/global-waf", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Backups ────────────────────────────────────────────────────────────

@mcp.tool(name="npg_download_backup", description="Download a backup by its ID. Returns the raw backup content.")
async def npg_download_backup(backup_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get_text(f"/api/v1/backups/{_id_path(backup_id)}/download")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_upload_restore_backup", description="Upload and restore from a backup file. REQUIRED: file_content.")
async def npg_upload_restore_backup(file_content: str) -> dict:
    c = _get_client()
    try:
        body = {"file": file_content}
        data = c.post("/api/v1/backups/upload-restore", body)
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
    """Require `Authorization: Bearer <token>` on every request.

    Returns the app unchanged if no MCP_API_TOKEN is configured (open mode,
    for local/LAN-only use). When set, unauthenticated/non-matching requests
    get a 401 and are never forwarded to MCP.
    """
    if not expected_token:
        return app

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    expected_bearer = f"Bearer {expected_token}"

    class _AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
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

@mcp.tool(name="npg_get_auth_account", description="GET own account info — returns the authenticated user's account details. NOTE: This endpoint is JWT-only (API tokens not accepted); falls back to JWT auth if needed.")
async def npg_get_auth_account() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/auth/account")
        return {"success": True, "data": data}
    except Exception as e:
        # JWT-only endpoint — retry with JWT client if API token failed
        if "401" in str(e) and os.environ.get("NPG_USERNAME") and os.environ.get("NPG_PASSWORD"):
            try:
                c2 = _get_jwt_client()
                data = c2.get("/api/v1/auth/account")
                return {"success": True, "data": data}
            except Exception as e2:
                return {"success": False, "error": str(e2)}
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_auth_change_credentials", description="Change own username and password (initial setup). REQUIRED: current_password, new_username, new_password. Used to complete forced initial setup.")
async def npg_auth_change_credentials(current_password: str, new_username: str, new_password: str) -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/auth/change-credentials", {"current_password": current_password, "new_username": new_username, "new_password": new_password})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_auth_change_username", description="Change own username. REQUIRED: current_password, new_username.")
async def npg_auth_change_username(current_password: str, new_username: str) -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/auth/change-username", {"current_password": current_password, "new_username": new_username})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_auth_2fa_setup", description="Begin 2FA enrolment — returns QR code / secret for the user to scan with their authenticator app. REQUIRED: password.")
async def npg_auth_2fa_setup(password: str) -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/auth/2fa/setup", {"password": password})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_auth_2fa_enable", description="Enable 2FA. REQUIRED: password, totp_code (6-digit code from authenticator).")
async def npg_auth_2fa_enable(password: str, totp_code: str) -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/auth/2fa/enable", {"password": password, "totp_code": totp_code})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_auth_2fa_disable", description="Disable 2FA. REQUIRED: password, totp_code.")
async def npg_auth_2fa_disable(password: str, totp_code: str) -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/auth/2fa/disable", {"password": password, "totp_code": totp_code})
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

@mcp.tool(name="npg_auth_sso_start", description="Begin an SSO login flow. REQUIRED: slug (the SSO provider identifier). Returns a redirect URL.")
async def npg_auth_sso_start(slug: str) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/auth/sso/{quote(slug, safe='')}/start")
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

@mcp.tool(name="npg_create_auth_provider", description="Create a ForwardAuth provider. REQUIRED: name, provider_type, config dict (provider-specific).")
async def npg_create_auth_provider(name: str, provider_type: str, config: dict | None = None, provider_url: str | None = None) -> dict:
    c = _get_client()
    try:
        body = {"name": name, "type": provider_type}
        if config is not None:
            body["config"] = config
        if provider_url is not None:
            body["provider_url"] = provider_url
        data = c.post("/api/v1/auth-providers", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_auth_provider", description="Get a ForwardAuth provider by its ID. REQUIRED: provider_id.")
async def npg_get_auth_provider(provider_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/auth-providers/{_id_path(provider_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_auth_provider", description="Update a ForwardAuth provider (partial update). Pass only fields to change. REQUIRED: provider_id.")
async def npg_update_auth_provider(provider_id: str | int, name: str | None = None, config: dict | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if name is not None: body["name"] = name
        if config is not None: body["config"] = config
        data = c.put(f"/api/v1/auth-providers/{_id_path(provider_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_auth_provider", description="Delete a ForwardAuth provider by its ID. REQUIRED: provider_id.")
async def npg_delete_auth_provider(provider_id: str | int) -> dict:
    c = _get_client()
    try:
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

@mcp.tool(name="npg_create_ddns_record", description="Create a DDNS record. REQUIRED: proxy_host_id, domain, provider_id. Optional: proxied (bool).")
async def npg_create_ddns_record(proxy_host_id: str | int, domain: str, provider_id: str | int, proxied: bool = False) -> dict:
    c = _get_client()
    try:
        data = c.post("/api/v1/ddns-records", {"proxy_host_id": _id_path(proxy_host_id), "domain": domain, "provider_id": _id_path(provider_id), "proxied": proxied})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_ddns_record", description="Get a DDNS record by its ID. REQUIRED: record_id.")
async def npg_get_ddns_record(record_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/ddns-records/{_id_path(record_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_ddns_record", description="Update a DDNS record (partial update). Pass only fields to change. REQUIRED: record_id.")
async def npg_update_ddns_record(record_id: str | int, domain: str | None = None, provider_id: str | int | None = None, proxied: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if domain is not None: body["domain"] = domain
        if provider_id is not None: body["provider_id"] = _id_path(provider_id)
        if proxied is not None: body["proxied"] = proxied
        data = c.put(f"/api/v1/ddns-records/{_id_path(record_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_ddns_record", description="Delete a DDNS record by its ID. REQUIRED: record_id.")
async def npg_delete_ddns_record(record_id: str | int) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.post(f"/api/v1/ddns-records/{_id_path(record_id)}/sync")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_import_ddns_from_hosts", description="Import DDNS records from existing proxy hosts that have DDNS enabled. REQUIRED: proxy_host_ids (list of host UUIDs), dns_provider_id (UUID of the DNS provider to use).")
async def npg_import_ddns_from_hosts(proxy_host_ids: list[str], dns_provider_id: str) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.post("/api/v1/filter-subscriptions/catalog/subscribe", {"paths": paths})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_filter_subscription", description="Subscribe to a filter list URL. REQUIRED: url. Optional: name.")
async def npg_create_filter_subscription(url: str, name: str | None = None) -> dict:
    c = _get_client()
    try:
        body = {"url": url}
        if name is not None:
            body["name"] = name
        data = c.post("/api/v1/filter-subscriptions", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_filter_subscription", description="Get a filter subscription with its entries and exclusions. REQUIRED: subscription_id.")
async def npg_get_filter_subscription(subscription_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_filter_subscription", description="Update a filter subscription (partial update). Pass only fields to change. REQUIRED: subscription_id.")
async def npg_update_filter_subscription(subscription_id: str | int, name: str | None = None, url: str | None = None, enabled: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if name is not None: body["name"] = name
        if url is not None: body["url"] = url
        if enabled is not None: body["enabled"] = enabled
        data = c.put(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_filter_subscription", description="Delete a filter subscription by its ID. REQUIRED: subscription_id.")
async def npg_delete_filter_subscription(subscription_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}")
        return {"success": True, "message": f"Filter subscription {_id_path(subscription_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_refresh_filter_subscription", description="Re-fetch entries for a filter subscription now. REQUIRED: subscription_id.")
async def npg_refresh_filter_subscription(subscription_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/refresh")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_filter_subscription_exclusions", description="List host exclusions of a filter subscription (hosts that skip this subscription). REQUIRED: subscription_id.")
async def npg_get_filter_subscription_exclusions(subscription_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/exclusions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_filter_subscription_exclusion", description="Exclude a proxy host from a filter subscription. REQUIRED: subscription_id, host_id.")
async def npg_add_filter_subscription_exclusion(subscription_id: str | int, host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/exclusions/{_id_path(host_id)}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_filter_subscription_exclusion", description="Remove a host exclusion from a filter subscription. REQUIRED: subscription_id, host_id.")
async def npg_remove_filter_subscription_exclusion(subscription_id: str | int, host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/exclusions/{_id_path(host_id)}")
        return {"success": True, "message": f"Exclusion removed for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_filter_subscription_entry_exclusions", description="List entry exclusions of a filter subscription (specific entries that are skipped). REQUIRED: subscription_id.")
async def npg_get_filter_subscription_entry_exclusions(subscription_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/entry-exclusions")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_filter_subscription_entry_exclusion", description="Exclude a single entry value from a filter subscription. REQUIRED: subscription_id, entry_value.")
async def npg_add_filter_subscription_entry_exclusion(subscription_id: str | int, entry_value: str) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/entry-exclusions", {"entry_value": entry_value})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_filter_subscription_entry_exclusion", description="Remove an entry exclusion from a filter subscription. REQUIRED: subscription_id, entry_value.")
async def npg_remove_filter_subscription_entry_exclusion(subscription_id: str | int, entry_value: str) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/filter-subscriptions/{_id_path(subscription_id)}/entry-exclusions", {"entry_value": entry_value})
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/exploit-rules/hosts/{_id_path(host_id)}/rules")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_exclude_exploit_rule_from_host", description="Exclude an exploit rule on ONE proxy host (stop it blocking there). REQUIRED: host_id, rule_id.")
async def npg_exclude_exploit_rule_from_host(host_id: str | int, rule_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/exploit-rules/hosts/{_id_path(host_id)}/rules/{_id_path(rule_id)}/exclude")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_exploit_rule_exclusion_from_host", description="Remove a host exclusion for an exploit rule (re-enable the rule for that host). REQUIRED: host_id, rule_id.")
async def npg_remove_exploit_rule_exclusion_from_host(host_id: str | int, rule_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/exploit-rules/hosts/{_id_path(host_id)}/rules/{_id_path(rule_id)}/exclude")
        return {"success": True, "message": f"Rule {_id_path(rule_id)} re-enabled for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_global_exclude_exploit_rule", description="Exclude an exploit rule on EVERY host (stop it blocking anywhere). REQUIRED: rule_id.")
async def npg_global_exclude_exploit_rule(rule_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/exploit-rules/{_id_path(rule_id)}/global-exclude")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_remove_exploit_rule_global_exclusion", description="Remove a global exclusion for an exploit rule (re-enable the rule everywhere). REQUIRED: rule_id.")
async def npg_remove_exploit_rule_global_exclusion(rule_id: str | int) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        c.delete(f"/api/v1/certificates/{_id_path(cert_id)}/error")
        return {"success": True, "message": f"Certificate {_id_path(cert_id)} error cleared"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_upload_certificate_pem", description="Replace the PEM material of a custom certificate. REQUIRED: cert_id, pem_content (full PEM string).")
async def npg_upload_certificate_pem(cert_id: str | int, pem_content: str) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/certificates/{_id_path(cert_id)}/upload", {"pem": pem_content})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_certificate_logs", description="Get the issuance log stream for a certificate. REQUIRED: cert_id.")
async def npg_get_certificate_logs(cert_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/certificates/{_id_path(cert_id)}/logs")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_certificate_download", description="Download certificate material (PEM/zip). REQUIRED: cert_id. Returns the raw content.")
async def npg_get_certificate_download(cert_id: str | int) -> dict:
    c = _get_client()
    try:
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
        body: dict = {}
        if enabled is not None: body["enabled"] = enabled
        if provider is not None: body["provider"] = provider
        if secret_key is not None: body["secret_key"] = secret_key
        if site_key is not None: body["site_key"] = site_key
        if challenge_type is not None: body["challenge_type"] = challenge_type
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
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        body = {"name": name, "filter": filter}
        if description is not None:
            body["description"] = description
        data = c.post("/api/v1/log-filter-presets", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_log_filter_preset", description="Update a log filter preset (rename and/or replace filter). REQUIRED: preset_id. Optional: name, filter, description.")
async def npg_update_log_filter_preset(preset_id: str | int, name: str | None = None, filter: dict | None = None, description: str | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if name is not None: body["name"] = name
        if filter is not None: body["filter"] = filter
        if description is not None: body["description"] = description
        data = c.put(f"/api/v1/log-filter-presets/{_id_path(preset_id)}", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_log_filter_preset", description="Delete a log filter preset by its ID. REQUIRED: preset_id.")
async def npg_delete_log_filter_preset(preset_id: str | int) -> dict:
    c = _get_client()
    try:
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
        body: dict = {}
        if max_age is not None: body["max_age"] = max_age
        if max_size is not None: body["max_size"] = max_size
        if max_files is not None: body["max_files"] = max_files
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


# ── Notification Channels Extras ───────────────────────────────────────
@mcp.tool(name="npg_get_notification_channel_deliveries", description="List recent deliveries for a notification channel. REQUIRED: channel_id.")
async def npg_get_notification_channel_deliveries(channel_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/notification-channels/{_id_path(channel_id)}/deliveries")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Proxy Host Extras ──────────────────────────────────────────────────

@mcp.tool(name="npg_set_proxy_host_favorite", description="Toggle a proxy host as a favorite. REQUIRED: host_id, favorite (bool).")
async def npg_set_proxy_host_favorite(host_id: str | int, favorite: bool) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit")
        return {"success": True, "message": f"Rate limit deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_bot_filter", description="Delete the bot filter config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_bot_filter(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter")
        return {"success": True, "message": f"Bot filter deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_security_headers", description="Delete the security headers config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_security_headers(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers")
        return {"success": True, "message": f"Security headers deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_upstream", description="Delete the upstream/load balancing config for a proxy host — host falls back to defaults. REQUIRED: host_id.")
async def npg_delete_proxy_host_upstream(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream")
        return {"success": True, "message": f"Upstream config deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_uri_block", description="Delete the URI block config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_uri_block(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block")
        return {"success": True, "message": f"URI block deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_fail2ban", description="Delete the fail2ban config for a proxy host — host falls back to global default. REQUIRED: host_id.")
async def npg_delete_proxy_host_fail2ban(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban")
        return {"success": True, "message": f"Fail2ban config deleted for host {_id_path(host_id)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_bulk_unban_ips", description="Unban multiple banned-IP records at once. REQUIRED: ids (list of record IDs).")
async def npg_bulk_unban_ips(ids: list[str | int]) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.get(f"/api/v1/banned-ips/history/ip/{quote(ip, safe='')}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_add_proxy_host_uri_block_rule", description="Add a single URI block rule to a proxy host. REQUIRED: host_id, pattern (str or regex). Optional: match_type ('exact'/'prefix'/'regex', default 'prefix'), description.")
async def npg_add_proxy_host_uri_block_rule(host_id: str | int, pattern: str, match_type: str = "prefix", description: str | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {"pattern": pattern, "match_type": match_type}
        if description is not None:
            body["description"] = description
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block/rules", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_uri_block_rule", description="Remove a single URI block rule from a proxy host. REQUIRED: host_id, rule_id.")
async def npg_delete_proxy_host_uri_block_rule(host_id: str | int, rule_id: str | int) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.post(f"/api/v1/settings/preset/{quote(preset, safe='')}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── System Extras ──────────────────────────────────────────────────────

@mcp.tool(name="npg_get_health_detailed", description="Get a detailed health snapshot (detailed version of health check). NOTE: This endpoint is JWT-only (API tokens not accepted); falls back to JWT auth if needed.")
async def npg_get_health_detailed() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/health/detailed")
        return {"success": True, "data": data}
    except Exception as e:
        # JWT-only endpoint — retry with JWT client if API token failed
        if "401" in str(e) and os.environ.get("NPG_USERNAME") and os.environ.get("NPG_PASSWORD"):
            try:
                c2 = _get_jwt_client()
                data = c2.get("/api/v1/health/detailed")
                return {"success": True, "data": data}
            except Exception as e2:
                return {"success": False, "error": str(e2)}
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_status", description="Get component status — health of all NPG subsystems. NOTE: This endpoint is JWT-only (API tokens not accepted); falls back to JWT auth if needed.")
async def npg_get_status() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/status")
        return {"success": True, "data": data}
    except Exception as e:
        # JWT-only endpoint — retry with JWT client if API token failed
        if "401" in str(e) and os.environ.get("NPG_USERNAME") and os.environ.get("NPG_PASSWORD"):
            try:
                c2 = _get_jwt_client()
                data = c2.get("/api/v1/status")
                return {"success": True, "data": data}
            except Exception as e2:
                return {"success": False, "error": str(e2)}
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_check_npg_update", description="Check for a newer NPG release version.")
async def npg_check_npg_update() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/system-settings/update/check")
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
    c = _get_client()
    try:
        data = c.post(f"/api/v1/waf/global/rules/{_id_path(rule_id)}/disable")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_enable_waf_global_rule", description="Re-enable a CRS rule globally (remove global disable). REQUIRED: rule_id.")
async def npg_enable_waf_global_rule(rule_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/waf/global/rules/{_id_path(rule_id)}/disable")
        return {"success": True, "message": f"WAF rule {_id_path(rule_id)} re-enabled globally"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_waf_host_history", description="Get the WAF policy change history for a proxy host. REQUIRED: host_id.")
async def npg_get_waf_host_history(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/waf/hosts/{_id_path(host_id)}/history")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_disable_waf_rule_by_host", description="Disable a CRS rule on the host that owns a domain name. REQUIRED: domain_name, rule_id.")
async def npg_disable_waf_rule_by_host(domain_name: str, rule_id: str | int) -> dict:
    c = _get_client()
    try:
        encoded = quote(domain_name, safe="")
        data = c.post(f"/api/v1/waf/rules/disable-by-host", {"domain_name": encoded, "rule_id": _id_path(rule_id)})
        return {"success": True, "data": data}
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
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.post("/api/v1/waf-test/test", {"target_url": target_url, "attack_type": attack_type})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_waf_all_patterns", description="Fire every attack payload at a target URL for comprehensive WAF testing. REQUIRED: target_url.")
async def npg_test_waf_all_patterns(target_url: str) -> dict:
    c = _get_client()
    try:
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
    c = _get_client()
    try:
        data = c.put(f"/api/v1/users/{_id_path(user_id)}/role", {"role_id": _id_path(role_id)})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        transport = "streamable-http"
    elif transport == "streamable-http":
        pass
    else:
        transport = "stdio"

    if transport == "stdio":
        mcp.run(transport=transport)
        return

    # HTTP transport: build the Starlette app and wrap it with bearer auth.
    import uvicorn

    app = mcp.streamable_http_app()
    token = os.environ.get("MCP_API_TOKEN", "").strip()
    app = _bearer_auth_middleware(app, token)

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8081"))
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level="info")
    )
    server.run()


if __name__ == "__main__":
    main()

"""NginxProxyGuard MCP server — streamable-http transport."""

from __future__ import annotations

import hmac
import os
from contextvars import ContextVar
from typing import Literal
from urllib.parse import quote

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
    """Get NPG client with auto-login from env credentials."""
    # Check for stored token first
    token = client_mod.get_token()
    if token:
        return client_mod.NPGClient(token=token)

    # Auto-login from env credentials
    username = os.environ.get("NPG_USERNAME", "")
    password = os.environ.get("NPG_PASSWORD", "")
    if username and password:
        c = client_mod.NPGClient()
        c.login(username, password)
        return c

    raise RuntimeError("NPG_USERNAME/NPG_PASSWORD environment variables not set.")


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

@mcp.tool(name="npg_get_proxy_host", description="Get a single proxy host by its ID.")
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

@mcp.tool(name="npg_create_proxy_host", description="Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: forward_scheme, block_normal, waf_enabled (default True), ssl_http2 (default True), ssl_http3 (default True), allow_websocket_upgrade (default True), block_http, ssl_forced, ssl_cert_id, cache_enabled, cache_static_only, cache_ttl, waf_use_global, waf_paranoia_level, waf_anomaly_threshold, waf_mode, block_exploits_exceptions, proxy_connect/send/read_timeout, proxy_buffering/request_buffering, client_max_body_size, proxy_max_temp_file_size, access_list_id, auth_provider_id, auth_bypass_paths, ddns_enabled/provider_id/proxied, forward_container_name/network, proxy_type, enabled, stream_* fields.")
async def npg_create_proxy_host(
    domain_names: list[str],
    forward_host: str,
    forward_port: int,
    forward_scheme: str = "http",
    block_normal: bool = False,
    waf_enabled: bool = True,
    block_http: bool = False,
    ssl_enabled: bool = True,
    ssl_forced: bool = True,
    ssl_http2: bool = True,
    ssl_http3: bool = False,
    ssl_cert_id: str | int | None = None,
    cache_enabled: bool = False,
    cache_static_only: bool = False,
    cache_ttl: str = "ignore",
    cache_template: str = "ignore",
    advanced_config: str = "",
    enable_proxy_headers: bool = True,
    host_header: str | None = None,
    extra_domains: list[str] | None = None,
    block_exploits: bool = False,
    block_exploits_exceptions: str | None = None,
    allow_websocket_upgrade: bool = True,
    waf_use_global: bool = False,
    waf_paranoia_level: int = 1,
    waf_anomaly_threshold: int = 5,
    waf_mode: str = "blocking",
    proxy_connect_timeout: int = 0,
    proxy_send_timeout: int = 0,
    proxy_read_timeout: int = 0,
    proxy_buffering: str = "on",
    proxy_request_buffering: str = "on",
    client_max_body_size: str = "off",
    proxy_max_temp_file_size: str = "off",
    access_list_id: str | int | None = None,
    auth_provider_id: str | int | None = None,
    auth_bypass_paths: list[str] | None = None,
    ddns_enabled: bool = False,
    ddns_provider_id: str | int | None = None,
    ddns_proxied: bool = False,
    forward_container_name: str | None = None,
    forward_container_network: str | None = None,
    proxy_type: str = "proxy",
    enabled: bool = True,
    stream_listen_host: str | None = None,
    stream_listen_port: int | None = None,
    stream_protocol: str = "tcp",
    stream_ssl_preread: bool = False,
    stream_accept_proxy_protocol: bool = False,
    stream_send_proxy_protocol: bool = False,
    stream_proxy_connect_timeout: int = 0,
    stream_proxy_timeout: int = 0,
) -> dict:
    c = _get_client()
    try:
        body = {
            "domain_names": domain_names,
            "forward_host": forward_host,
            "forward_port": forward_port,
            "forward_scheme": forward_scheme,
            "block_normal_access": block_normal,
            "waf_enabled": waf_enabled,
            "block_http_requests": block_http,
            "ssl_enabled": ssl_enabled,
            "ssl_force_https": ssl_forced,
            "ssl_http2": ssl_http2,
            "ssl_http3": ssl_http3,
            "certificate_id": ssl_cert_id,
            "cache_enabled": cache_enabled,
            "cache_static_only": cache_static_only,
            "cache_ttl": cache_ttl,
            "cache_template": cache_template,
            "advanced_config": advanced_config,
            "enable_proxy_headers": enable_proxy_headers,
            "pass_host_header": host_header,
            "extra_domains": extra_domains or [],
            "block_exploits": block_exploits,
            "block_exploits_exceptions": block_exploits_exceptions,
            "allow_websocket_upgrade": allow_websocket_upgrade,
            "waf_use_global": waf_use_global,
            "waf_paranoia_level": waf_paranoia_level,
            "waf_anomaly_threshold": waf_anomaly_threshold,
            "waf_mode": waf_mode,
            "proxy_connect_timeout": proxy_connect_timeout,
            "proxy_send_timeout": proxy_send_timeout,
            "proxy_read_timeout": proxy_read_timeout,
            "proxy_buffering": proxy_buffering,
            "proxy_request_buffering": proxy_request_buffering,
            "client_max_body_size": client_max_body_size,
            "proxy_max_temp_file_size": proxy_max_temp_file_size,
            "access_list_id": _id_path(access_list_id) if access_list_id is not None else None,
            "auth_provider_id": _id_path(auth_provider_id) if auth_provider_id is not None else None,
            "auth_bypass_paths": auth_bypass_paths or [],
            "ddns_enabled": ddns_enabled,
            "ddns_provider_id": _id_path(ddns_provider_id) if ddns_provider_id is not None else None,
            "ddns_proxied": ddns_proxied,
            "forward_container_name": forward_container_name,
            "forward_container_network": forward_container_network,
            "proxy_type": proxy_type,
            "enabled": enabled,
            "stream_listen_host": stream_listen_host,
            "stream_listen_port": stream_listen_port,
            "stream_protocol": stream_protocol,
            "stream_ssl_preread": stream_ssl_preread,
            "stream_accept_proxy_protocol": stream_accept_proxy_protocol,
            "stream_send_proxy_protocol": stream_send_proxy_protocol,
            "stream_proxy_connect_timeout": stream_proxy_connect_timeout,
            "stream_proxy_timeout": stream_proxy_timeout,
        }
        data = c.post("/api/v1/proxy-hosts", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host", description="Update an existing proxy host. Pass only the fields you want to change. Use `?skip_nginx=true` to skip nginx regeneration. NEW: waf_use_global, waf_paranoia_level, waf_anomaly_threshold, proxy_connect/send/read_timeout, proxy_buffering/request_buffering, client_max_body_size, proxy_max_temp_file_size, access_list_id, auth_provider_id, auth_bypass_paths, ddns_enabled/provider_id/proxied, forward_container_name/network, cache_static_only, cache_ttl, block_exploits_exceptions.")
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
    cache_ttl: int | None = None,
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
    proxy_buffering: bool | None = None,
    proxy_request_buffering: bool | None = None,
    client_max_body_size: int | None = None,
    proxy_max_temp_file_size: int | None = None,
    access_list_id: str | int | None = None,
    auth_provider_id: str | int | None = None,
    auth_bypass_paths: str | None = None,
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

@mcp.tool(name="npg_delete_proxy_host", description="Delete a proxy host by its ID.")
async def npg_delete_proxy_host(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}")
        return {"success": True, "message": f"Proxy host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_proxy_host", description="Test upstream connectivity for a proxy host.")
async def npg_test_proxy_host(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/test")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_regenerate_config", description="Regenerate nginx config for a specific proxy host without touching others.")
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

@mcp.tool(name="npg_clone_proxy_host", description="Clone a proxy host with new domain names. Returns the new proxy host.")
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

@mcp.tool(name="npg_get_certificate", description="Get a certificate by its ID.")
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

@mcp.tool(name="npg_delete_certificate", description="Delete a certificate by its ID.")
async def npg_delete_certificate(cert_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/certificates/{_id_path(cert_id)}")
        return {"success": True, "message": f"Certificate {_id_path(cert_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_renew_certificate", description="Renew a certificate by its ID.")
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

@mcp.tool(name="npg_get_redirect_host", description="Get a redirect host by its ID.")
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

@mcp.tool(name="npg_update_redirect_host", description="Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code.")
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

@mcp.tool(name="npg_delete_redirect_host", description="Delete a redirect host by its ID.")
async def npg_delete_redirect_host(host_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/redirect-hosts/{_id_path(host_id)}")
        return {"success": True, "message": f"Redirect host {_id_path(host_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Security Features (per proxy host) ────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_rate_limit", description="GET rate limit configuration for a proxy host.")
async def npg_get_proxy_host_rate_limit(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_rate_limit", description="UPDATE rate limit configuration for a proxy host. Body: enabled, requests_per_second, burst_size, zone_size, limit_by (ip/uri/ip_uri), limit_response")
async def npg_update_proxy_host_rate_limit(host_id: str | int, enabled: bool, requests_per_second: int, burst_size: int, zone_size: str = "10m", limit_by: str = "ip", limit_response: int = 429) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/rate-limit", {"enabled": enabled, "requests_per_second": requests_per_second, "burst_size": burst_size, "zone_size": zone_size, "limit_by": limit_by, "limit_response": limit_response})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_bot_filter", description="GET bot filter configuration for a proxy host.")
async def npg_get_proxy_host_bot_filter(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_bot_filter", description="UPDATE bot filter configuration for a proxy host. Required: host_id (str|int), enabled (bool). Optional: block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool), custom_blocked_agents (str, comma-separated list), custom_allowed_agents (str, comma-separated list).")
async def npg_update_proxy_host_bot_filter(host_id: str | int, enabled: bool, block_bad_bots: bool = True, block_ai_bots: bool = False, allow_search_engines: bool = True, block_suspicious_clients: bool = False, challenge_suspicious: bool = False, disable_global: bool = False, custom_blocked_agents: str | None = None, custom_allowed_agents: str | None = None) -> dict:
    c = _get_client()
    try:
        body = {"enabled": enabled, "block_bad_bots": block_bad_bots, "block_ai_bots": block_ai_bots, "allow_search_engines": allow_search_engines, "block_suspicious_clients": block_suspicious_clients, "challenge_suspicious": challenge_suspicious, "disable_global": disable_global}
        if custom_blocked_agents is not None:
            body["custom_blocked_agents"] = custom_blocked_agents
        if custom_allowed_agents is not None:
            body["custom_allowed_agents"] = custom_allowed_agents
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/bot-filter", body)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_security_headers", description="GET security headers configuration for a proxy host.")
async def npg_get_proxy_host_security_headers(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_security_headers", description="UPDATE security headers for a proxy host. Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options (DENY/SAMEORIGIN/''), x_content_type_options, x_xss_protection, referrer_policy, content_security_policy")
async def npg_update_proxy_host_security_headers(host_id: str | int, enabled: bool, hsts_enabled: bool = True, hsts_max_age: int = 31536000, hsts_include_subdomains: bool = True, hsts_preload: bool = False, x_frame_options: str = "SAMEORIGIN", x_content_type_options: bool = True, x_xss_protection: bool = True, referrer_policy: str = "strict-origin-when-cross-origin", content_security_policy: str = "") -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers", {"enabled": enabled, "hsts_enabled": hsts_enabled, "hsts_max_age": hsts_max_age, "hsts_include_subdomains": hsts_include_subdomains, "hsts_preload": hsts_preload, "x_frame_options": x_frame_options, "x_content_type_options": x_content_type_options, "x_xss_protection": x_xss_protection, "referrer_policy": referrer_policy, "content_security_policy": content_security_policy})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_apply_security_header_preset", description="APPLY a security header preset to a proxy host. preset: strict, balanced, or relaxed.")
async def npg_apply_security_header_preset(host_id: str | int, preset: Literal["strict", "balanced", "relaxed"]) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/security-headers/preset/{preset}")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_upstream", description="GET upstream/load balancing configuration for a proxy host.")
async def npg_get_proxy_host_upstream(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_upstream", description="UPDATE upstream/load balancing configuration. Body: name, scheme, servers (list of {address, port, weight, backup}), load_balance, health_check_enabled, health_check_path, health_check_interval")
async def npg_update_proxy_host_upstream(host_id: str | int, scheme: str = "http", servers: list[dict] | None = None, load_balance: str = "round_robin", health_check_enabled: bool = False, health_check_path: str = "/", health_check_interval: int = 10) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/upstream", {"scheme": scheme, "servers": servers or [], "load_balance": load_balance, "health_check_enabled": health_check_enabled, "health_check_path": health_check_path, "health_check_interval": health_check_interval})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_get_proxy_host_uri_block", description="GET URI block configuration for a proxy host.")
async def npg_get_proxy_host_uri_block(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_uri_block", description="UPDATE URI block configuration. Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips")
async def npg_update_proxy_host_uri_block(host_id: str | int, enabled: bool, rules: list[dict] | None = None, exception_ips: list[str] | None = None, allow_private_ips: bool = True) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/uri-block", {"enabled": enabled, "rules": rules or [], "exception_ips": exception_ips or [], "allow_private_ips": allow_private_ips})
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

@mcp.tool(name="npg_get_access_list", description="Get an access list by its ID.")
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

@mcp.tool(name="npg_update_access_list", description="Update an access list. Pass only fields to change.")
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

@mcp.tool(name="npg_delete_access_list", description="Delete an access list by its ID.")
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

@mcp.tool(name="npg_get_dns_provider", description="Get a DNS provider by its ID.")
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

@mcp.tool(name="npg_update_dns_provider", description="Update a DNS provider. Pass only fields to change (dict).")
async def npg_update_dns_provider(provider_id: str | int, kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/dns-providers/{_id_path(provider_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_dns_provider", description="Delete a DNS provider by its ID.")
async def npg_delete_dns_provider(provider_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/dns-providers/{_id_path(provider_id)}")
        return {"success": True, "message": f"DNS provider {_id_path(provider_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_test_dns_provider", description="Test DNS provider credentials.")
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

@mcp.tool(name="npg_get_proxy_host_cloud_blocking", description="GET per-host cloud provider blocking configuration. Returns blocked_providers, challenge_mode, allow_search_bots, cloud_disable_global.")
async def npg_get_proxy_host_cloud_blocking(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/blocked-cloud-providers")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_cloud_blocking", description="UPDATE per-host cloud provider blocking. Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool), cloud_disable_global (bool).")
async def npg_update_proxy_host_cloud_blocking(host_id: str | int, blocked_providers: list[str] | None = None, challenge_mode: bool | None = None, allow_search_bots: bool | None = None, cloud_disable_global: bool | None = None) -> dict:
    c = _get_client()
    try:
        body: dict = {}
        if blocked_providers is not None: body["blocked_providers"] = blocked_providers
        if challenge_mode is not None: body["challenge_mode"] = challenge_mode
        if allow_search_bots is not None: body["allow_search_bots"] = allow_search_bots
        if cloud_disable_global is not None: body["cloud_disable_global"] = cloud_disable_global
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

@mcp.tool(name="npg_get_proxy_host_geo", description="GET geo restriction configuration for a proxy host.")
async def npg_get_proxy_host_geo(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_create_proxy_host_geo", description="CREATE geo restriction for a proxy host. Body: enabled, mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode, disable_global, allow_private_ips, allow_search_bots")
async def npg_create_proxy_host_geo(host_id: str | int, enabled: bool, mode: Literal["whitelist", "blacklist"] = "blacklist", countries: list[str] | None = None, allowed_ips: list[str] | None = None, challenge_mode: bool = False, disable_global: bool = False, allow_private_ips: bool = True, allow_search_bots: bool = True) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo", {"enabled": enabled, "mode": mode, "countries": countries or [], "allowed_ips": allowed_ips or [], "challenge_mode": challenge_mode, "disable_global": disable_global, "allow_private_ips": allow_private_ips, "allow_search_bots": allow_search_bots})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_geo", description="UPDATE geo restriction for a proxy host. Body: enabled, mode, countries, allowed_ips, challenge_mode, disable_global, allow_private_ips, allow_search_bots")
async def npg_update_proxy_host_geo(host_id: str | int, enabled: bool, mode: Literal["whitelist", "blacklist"] = "blacklist", countries: list[str] | None = None, allowed_ips: list[str] | None = None, challenge_mode: bool = False, disable_global: bool = False, allow_private_ips: bool = True, allow_search_bots: bool = True) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo", {"enabled": enabled, "mode": mode, "countries": countries or [], "allowed_ips": allowed_ips or [], "challenge_mode": challenge_mode, "disable_global": disable_global, "allow_private_ips": allow_private_ips, "allow_search_bots": allow_search_bots})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_geo", description="DELETE geo restriction for a proxy host.")
async def npg_delete_proxy_host_geo(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/geo")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Fail2ban (per proxy host) ─────────────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_fail2ban", description="GET fail2ban configuration for a proxy host.")
async def npg_get_proxy_host_fail2ban(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_fail2ban", description="UPDATE fail2ban configuration. Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge)")
async def npg_update_proxy_host_fail2ban(host_id: str | int, enabled: bool, max_retries: int = 5, find_time: int = 600, ban_time: int = 3600, fail_codes: str = "401,403", action: Literal["block", "challenge"] = "block") -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/fail2ban", {"enabled": enabled, "max_retries": max_retries, "find_time": find_time, "ban_time": ban_time, "fail_codes": fail_codes, "action": action})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Challenge/CAPTCHA (per proxy host) ────────────────────────────────

@mcp.tool(name="npg_get_proxy_host_challenge", description="GET CAPTCHA/challenge configuration for a proxy host.")
async def npg_get_proxy_host_challenge(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_proxy_host_challenge", description="UPDATE CAPTCHA/challenge configuration. Body: enabled, challenge_type (captcha/js_challenge), difficulty, site_key, token_validity, min_score, apply_to, page_title, challenge_ips")
async def npg_update_proxy_host_challenge(host_id: str | int, enabled: bool, challenge_type: str = "captcha", difficulty: str = "medium", site_key: str = "", token_validity: int = 86400, min_score: float = 0.5, apply_to: str = "both", page_title: str = "Security Check") -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge", {"enabled": enabled, "challenge_type": challenge_type, "difficulty": difficulty, "site_key": site_key, "token_validity": token_validity, "min_score": min_score, "apply_to": apply_to, "page_title": page_title})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_proxy_host_challenge", description="DELETE CAPTCHA/challenge configuration for a proxy host.")
async def npg_delete_proxy_host_challenge(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.delete(f"/api/v1/proxy-hosts/{_id_path(host_id)}/challenge")
        return {"success": True, "data": data}
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

@mcp.tool(name="npg_ban_ip", description="Ban an IP address. Required: ip. Optional: ban_time (seconds).")
async def npg_ban_ip(ip_address: str, reason: str = "Manual ban via API", duration: int = 3600) -> dict:
    """Ban an IP address. Required: ip_address. Optional: reason, duration (seconds, 0=permanent)."""
    c = _get_client()
    try:
        data = c.post("/api/v1/banned-ips", {"ip_address": ip_address, "reason": reason, "duration": duration})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_unban_ip", description="Unban an IP by its ID.")
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

@mcp.tool(name="npg_get_global_uri_block", description="Get global URI block settings.")
async def npg_get_global_uri_block() -> dict:
    c = _get_client()
    try:
        data = c.get("/api/v1/global-uri-block")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_update_global_uri_block", description="Update global URI block settings. Pass only fields to change (dict).")
async def npg_update_global_uri_block(kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put("/api/v1/global-uri-block", kwargs or {})
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

@mcp.tool(name="npg_get_exploit_rule", description="Get an exploit rule by its ID.")
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

@mcp.tool(name="npg_update_exploit_rule", description="Update an exploit rule. Pass only fields to change (dict).")
async def npg_update_exploit_rule(rule_id: str | int, kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/exploit-rules/{_id_path(rule_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_exploit_rule", description="Delete an exploit rule by its ID.")
async def npg_delete_exploit_rule(rule_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/exploit-rules/{_id_path(rule_id)}")
        return {"success": True, "message": f"Exploit rule {_id_path(rule_id)} deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_toggle_exploit_rule", description="Toggle an exploit rule's enabled status.")
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

@mcp.tool(name="npg_get_waf_host_config", description="Get WAF config for a specific proxy host.")
async def npg_get_waf_host_config(host_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.get(f"/api/v1/waf/hosts/{_id_path(host_id)}/config")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_disable_waf_rule", description="Disable a WAF rule for a specific proxy host.")
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

@mcp.tool(name="npg_get_backup", description="Get a backup by its ID.")
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

@mcp.tool(name="npg_delete_backup", description="Delete a backup by its ID.")
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

@mcp.tool(name="npg_get_api_token", description="Get an API token by its ID.")
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

@mcp.tool(name="npg_update_api_token", description="Update an API token. Pass only fields to change (dict).")
async def npg_update_api_token(token_id: str | int, kwargs: dict | None = None) -> dict:
    c = _get_client()
    try:
        data = c.put(f"/api/v1/api-tokens/{_id_path(token_id)}", kwargs or {})
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_revoke_api_token", description="Revoke an API token by its ID.")
async def npg_revoke_api_token(token_id: str | int) -> dict:
    c = _get_client()
    try:
        data = c.post(f"/api/v1/api-tokens/{_id_path(token_id)}/revoke")
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(name="npg_delete_api_token", description="Delete an API token by its ID.")
async def npg_delete_api_token(token_id: str | int) -> dict:
    c = _get_client()
    try:
        c.delete(f"/api/v1/api-tokens/{_id_path(token_id)}")
        return {"success": True, "message": f"API token {_id_path(token_id)} deleted"}
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

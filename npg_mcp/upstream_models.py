"""Upstream NPG API request-model field whitelists for kwargs-dict validation.

The Go API silently ignores unknown JSON fields, so a typo'd key in a
``kwargs`` dict (e.g. ``log_retention_days`` on npg_update_log_settings,
whose real field is ``retention_days``) returns success while changing
nothing — the silent-noop bug class behind the historical FastMCP
``**kwargs`` double-nesting incident. Each frozenset below is transcribed
from the upstream request struct (api/internal/model/*.go) at NPG v2.51.0.

Maintenance: when upstream adds fields to one of these structs, add the new
key here in the same commit that re-verifies against the latest tag.
Callers who must bypass validation (e.g. a brand-new upstream field the MCP
hasn't whitelisted yet) can pass ``strict=False`` on the tool call.
"""

from __future__ import annotations

# Tool name -> accepted JSON field names of the upstream request model.
TOOL_KWARGS_WHITELIST: dict[str, frozenset[str]] = {
    # model/global_settings.go: UpdateGlobalSettingsRequest
    "npg_update_settings": frozenset({
        "worker_processes", "worker_connections", "worker_rlimit_nofile",
        "multi_accept", "use_epoll",
        "sendfile", "tcp_nopush", "tcp_nodelay", "keepalive_timeout",
        "keepalive_requests", "types_hash_max_size", "server_tokens",
        "client_body_buffer_size", "client_header_buffer_size",
        "client_max_body_size", "large_client_header_buffers",
        "client_body_timeout", "client_header_timeout", "send_timeout",
        "proxy_connect_timeout", "proxy_send_timeout", "proxy_read_timeout",
        "gzip_enabled", "gzip_vary", "gzip_proxied", "gzip_comp_level",
        "gzip_buffers", "gzip_http_version", "gzip_min_length", "gzip_types",
        "brotli_enabled", "brotli_static", "brotli_comp_level",
        "brotli_min_length", "brotli_types",
        "proxy_buffer_size", "proxy_buffers", "proxy_busy_buffers_size",
        "proxy_max_temp_file_size", "proxy_temp_file_write_size",
        "proxy_buffering", "proxy_request_buffering",
        "open_file_cache_enabled", "open_file_cache_max",
        "open_file_cache_inactive", "open_file_cache_valid",
        "open_file_cache_min_uses", "open_file_cache_errors",
        "ssl_protocols", "ssl_ciphers", "ssl_prefer_server_ciphers",
        "ssl_session_cache", "ssl_session_timeout", "ssl_session_tickets",
        "ssl_stapling", "ssl_stapling_verify", "ssl_ecdh_curve",
        "access_log_enabled", "access_log_strip_query", "error_log_level",
        "resolver", "resolver_timeout",
        "custom_http_config", "custom_stream_config",
        "direct_ip_access_action", "enable_ipv6",
        "limit_conn_enabled", "limit_conn_zone_size", "limit_conn_per_ip",
        "limit_req_enabled", "limit_req_zone_size", "limit_req_rate",
        "limit_req_burst", "reset_timedout_connection",
        "limit_rate", "limit_rate_after",
    }),
    # model/system_settings.go: UpdateSystemSettingsRequest
    "npg_update_system_settings": frozenset({
        "geoip_enabled", "maxmind_license_key", "maxmind_account_id",
        "geoip_auto_update", "geoip_update_interval",
        "acme_enabled", "acme_email", "acme_staging", "acme_auto_renew",
        "acme_renew_days_before", "acme_dns_provider", "acme_dns_credentials",
        "notification_email", "notify_cert_expiry", "notify_cert_expiry_days",
        "notify_security_events", "notify_backup_complete",
        "log_retention_days", "stats_retention_days",
        "backup_retention_count", "auto_backup_enabled", "auto_backup_schedule",
        "ddns_check_interval_minutes",
        "access_log_retention_days", "waf_log_retention_days",
        "error_log_retention_days", "system_log_retention_days",
        "audit_log_retention_days",
        "raw_log_enabled", "raw_log_retention_days", "raw_log_max_size_mb",
        "raw_log_rotate_count", "raw_log_compress_rotated",
        "bot_filter_default_enabled", "bot_filter_default_block_bad_bots",
        "bot_filter_default_block_ai_bots",
        "bot_filter_default_allow_search_engines",
        "bot_filter_default_block_suspicious_clients",
        "bot_filter_default_challenge_suspicious",
        "bot_filter_default_custom_blocked_agents",
        "bot_list_bad_bots", "bot_list_ai_bots", "bot_list_search_engines",
        "bot_list_suspicious_clients",
        "waf_auto_ban_enabled", "waf_auto_ban_threshold",
        "waf_auto_ban_window", "waf_auto_ban_duration",
        "global_trusted_ips", "global_trusted_ips_bypass_waf",
        "global_block_exploits_exceptions", "direct_ip_access_action",
        "ui_font_family", "ui_error_page_language",
        "system_logs_enabled", "system_logs_levels",
        "system_logs_exclude_patterns", "system_logs_stdout_excluded",
        # v2.51.0
        "trusted_proxy_cidrs", "trusted_proxy_preset", "real_ip_header",
    }),
    # model/log.go: UpdateLogSettingsRequest
    "npg_update_log_settings": frozenset({
        "retention_days", "max_logs_per_type", "auto_cleanup_enabled",
    }),
    # model/dns_provider.go
    "npg_create_dns_provider": frozenset({
        "name", "provider_type", "credentials", "is_default",
    }),
    "npg_update_dns_provider": frozenset({
        "name", "credentials", "is_default",
    }),
    # model/cloud_provider.go
    "npg_create_cloud_provider": frozenset({
        "name", "slug", "region", "description", "ip_ranges", "ip_ranges_url",
    }),
    "npg_update_cloud_provider": frozenset({
        "name", "description", "ip_ranges", "ip_ranges_url", "enabled",
    }),
    # model/exploit_block_rule.go
    "npg_create_exploit_rule": frozenset({
        "category", "name", "pattern", "pattern_type", "description", "severity",
    }),
    "npg_update_exploit_rule": frozenset({
        "name", "pattern", "pattern_type", "description", "severity", "enabled",
    }),
    # model/api_token.go
    "npg_update_api_token": frozenset({
        "name", "permissions", "allowed_ips", "rate_limit", "is_active",
    }),
    # model/cloudflare_tunnel.go: UpdateCloudflareTunnelRequest
    "npg_update_cloudflare_tunnel": frozenset({
        "enabled", "token", "mode", "api_token", "catchall_enabled",
    }),
}


def _validate_kwargs(tool_name: str, kwargs: dict | None, strict: bool = True) -> None:
    """Reject unknown keys in a kwargs dict before any API call is made.

    None/empty dicts always pass. With strict=True (default), any key not in
    the upstream whitelist raises ValueError naming the offending keys and
    the full accepted list — turning a silent server-side no-op into an
    immediate, self-explanatory client-side error. strict=False bypasses the
    check entirely (escape hatch for newer upstream fields).
    """
    if not strict or not kwargs:
        return
    allowed = TOOL_KWARGS_WHITELIST.get(tool_name)
    if allowed is None:  # un-whitelisted tool: fail open rather than break callers
        return
    unknown = sorted(set(kwargs) - allowed)
    if unknown:
        raise ValueError(
            f"{tool_name}: unknown field(s) {unknown}. "
            f"Accepted fields: {sorted(allowed)}. "
            f"Pass strict=false to bypass this check."
        )

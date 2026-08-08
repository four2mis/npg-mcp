# NPG MCP Server

**English** | [한국어](README.ko.md)

MCP server for [NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard) (NPG) — manage proxy hosts, certificates, SSL, security rules, and nginx configuration through MCP tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org/).

> **⚠️ Vibe-coded with an AI agent.** This codebase was generated at speed by an AI agent, not hand-crafted by a human. Expect rough edges, unhandled edge cases, and bugs. Do **not** deploy it to an active/production NginxProxyGuard instance without first testing against a **sandboxed / disposable NPG environment** and reviewing the code. It can create, update, delete, and reconfigure live proxy hosts, so verify in isolation before pointing it at real infrastructure.

## Tools Reference

This server exposes **180 MCP tools**. Each tool is documented below with a short description and its **input parameter schema** (parameter, type, whether it is required, and default value). Tools are grouped into the following categories:

- **Dashboard** — 6 tools
- **Proxy Hosts** — 10 tools
- **SSL / Nginx** — 8 tools
- **Redirect Hosts** — 5 tools
- **Security (per-host)** — 12 tools
- **Geo Restriction** — 5 tools
- **Fail2ban & Challenge** — 6 tools
- **Access Lists** — 5 tools
- **DNS Providers** — 6 tools
- **Cloud Providers** — 9 tools
- **GeoIP** — 2 tools
- **Banned IPs & Bots** — 4 tools
- **URI Block** — 4 tools
- **Global URI Block** — 4 tools
- **WAF & Exploit Rules** — 10 tools
- **Settings** — 4 tools
- **Global Settings** — 7 tools
- **Logs** — 10 tools
- **Backups** — 8 tools
- **API Tokens** — 6 tools
- **Users** — 8 tools
- **Roles** — 5 tools
- **SSO Providers** — 6 tools
- **Notification Channels** — 8 tools
- **Catalog** — 2 tools
- **Docker** — 2 tools

### Dashboard (6)

#### `npg_get_dashboard`

Get dashboard data (summary of proxy hosts, certificates, etc.).

_No parameters._

#### `npg_get_dashboard_health`

Get system health status.

_No parameters._

#### `npg_get_dashboard_geoip_stats`

GET GeoIP statistics by country for the dashboard.

_No parameters._

#### `npg_get_dashboard_containers`

Get Docker container statistics for the dashboard.

_No parameters._

#### `npg_get_dashboard_stats`

Get hourly statistics for the dashboard.

_No parameters._

#### `npg_get_dashboard_health_history`

Get system health history for the dashboard.

_No parameters._

### Proxy Hosts (10)

#### `npg_list_proxy_hosts`

List all proxy hosts. Returns a list of proxy host objects.

_No parameters._

#### `npg_get_proxy_host`

Get a single proxy host by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_get_proxy_host_by_domain`

Get a proxy host by its domain name.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `domain` | `string` | ✔ |  |

#### `npg_create_proxy_host`

Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: forward_scheme, block_normal, waf_enabled (default True), ssl_http2 (default True), ssl_http3 (default True), allow_websocket_upgrade (default True), block_http, ssl_forced, ssl_cert_id, cache_enabled, cache_static_only, cache_ttl, waf_use_global, waf_paranoia_level, waf_anomaly_threshold, waf_mode, block_exploits_exceptions, proxy_connect/send/read_timeout, proxy_buffering/request_buffering, client_max_body_size, proxy_max_temp_file_size, access_list_id, auth_provider_id, auth_bypass_paths, ddns_enabled/provider_id/proxied, forward_container_name/network, proxy_type, enabled, stream_* fields.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `domain_names` | `array<string>` | ✔ |  |
| `forward_host` | `string` | ✔ |  |
| `forward_port` | `int` | ✔ |  |
| `forward_scheme` | `string` | — | `"http"` |
| `block_normal` | `bool` | — | `false` |
| `waf_enabled` | `bool` | — | `true` |
| `block_http` | `bool` | — | `false` |
| `ssl_enabled` | `bool` | — | `true` |
| `ssl_forced` | `bool` | — | `true` |
| `ssl_http2` | `bool` | — | `true` |
| `ssl_http3` | `bool` | — | `false` |
| `ssl_cert_id` | `string/int/null` | — | `null` |
| `cache_enabled` | `bool` | — | `false` |
| `cache_static_only` | `bool` | — | `false` |
| `cache_ttl` | `string` | — | `"ignore"` |
| `cache_template` | `string` | — | `"ignore"` |
| `advanced_config` | `string` | — | `""` |
| `enable_proxy_headers` | `bool` | — | `true` |
| `host_header` | `string/null` | — | `null` |
| `extra_domains` | `array<any>/null` | — | `null` |
| `block_exploits` | `bool` | — | `false` |
| `block_exploits_exceptions` | `str/null` | — | `null` |
| `allow_websocket_upgrade` | `bool` | — | `true` |
| `waf_use_global` | `bool` | — | `false` |
| `waf_paranoia_level` | `int` | — | `1` |
| `waf_anomaly_threshold` | `int` | — | `5` |
| `waf_mode` | `string` | — | `"blocking"` |
| `proxy_connect_timeout` | `int` | — | `0` |
| `proxy_send_timeout` | `int` | — | `0` |
| `proxy_read_timeout` | `int` | — | `0` |
| `proxy_buffering` | `string` | — | `"on"` |
| `proxy_request_buffering` | `string` | — | `"on"` |
| `client_max_body_size` | `string` | — | `"off"` |
| `proxy_max_temp_file_size` | `string` | — | `"off"` |
| `access_list_id` | `str/int/null` | — | `null` |
| `auth_provider_id` | `str/int/null` | — | `null` |
| `auth_bypass_paths` | `array<str>/null` | — | `null` |
| `ddns_enabled` | `bool` | — | `false` |
| `ddns_provider_id` | `str/int/null` | — | `null` |
| `ddns_proxied` | `bool` | — | `false` |
| `forward_container_name` | `str/null` | — | `null` |
| `forward_container_network` | `str/null` | — | `null` |
| `proxy_type` | `string` | — | `"proxy"` |
| `enabled` | `bool` | — | `true` |
| `stream_listen_host` | `str/null` | — | `null` |
| `stream_listen_port` | `int/null` | — | `null` |
| `stream_protocol` | `string` | — | `"tcp"` |
| `stream_ssl_preread` | `bool` | — | `false` |
| `stream_accept_proxy_protocol` | `bool` | — | `false` |
| `stream_send_proxy_protocol` | `bool` | — | `false` |
| `stream_proxy_connect_timeout` | `int` | — | `0` |
| `stream_proxy_timeout` | `int` | — | `0` |

#### `npg_update_proxy_host`

Update an existing proxy host. Pass only the fields you want to change. Use `?skip_nginx=true` to skip nginx regeneration.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `domain_names` | `array<any>/null` | — | `null` |
| `forward_host` | `string/null` | — | `null` |
| `forward_port` | `int/null` | — | `null` |
| `forward_scheme` | `string/null` | — | `null` |
| `block_normal` | `bool/null` | — | `null` |
| `waf_enabled` | `bool/null` | — | `null` |
| `block_http` | `bool/null` | — | `null` |
| `ssl_forced` | `bool/null` | — | `null` |
| `ssl_cert_id` | `string/int/null` | — | `null` |
| `cache_enabled` | `bool/null` | — | `null` |
| `cache_template` | `string/null` | — | `null` |
| `advanced_config` | `string/null` | — | `null` |
| `enable_proxy_headers` | `bool/null` | — | `null` |
| `host_header` | `string/null` | — | `null` |
| `extra_domains` | `array<any>/null` | — | `null` |
| `enabled` | `bool/null` | — | `null` |
| `ssl_http2` | `bool/null` | — | `null` |
| `ssl_http3` | `bool/null` | — | `null` |
| `block_exploits` | `bool/null` | — | `null` |
| `skip_nginx` | `bool` | — | `false` |
| `waf_use_global` | `bool/null` | — | `null` |
| `waf_paranoia_level` | `int/null` | — | `null` |
| `waf_anomaly_threshold` | `int/null` | — | `null` |
| `block_exploits_exceptions` | `str/null` | — | `null` |
| `proxy_connect_timeout` | `int/null` | — | `null` |
| `proxy_send_timeout` | `int/null` | — | `null` |
| `proxy_read_timeout` | `int/null` | — | `null` |
| `proxy_buffering` | `bool/null` | — | `null` |
| `proxy_request_buffering` | `bool/null` | — | `null` |
| `client_max_body_size` | `int/null` | — | `null` |
| `proxy_max_temp_file_size` | `int/null` | — | `null` |
| `access_list_id` | `str/null` | — | `null` |
| `auth_provider_id` | `str/null` | — | `null` |
| `auth_bypass_paths` | `str/null` | — | `null` |
| `ddns_enabled` | `bool/null` | — | `null` |
| `ddns_provider_id` | `str/null` | — | `null` |
| `ddns_proxied` | `bool/null` | — | `null` |
| `forward_container_name` | `str/null` | — | `null` |
| `forward_container_network` | `str/null` | — | `null` |
| `cache_static_only` | `bool/null` | — | `null` |
| `cache_ttl` | `int/null` | — | `null` |

#### `npg_delete_proxy_host`

Delete a proxy host by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_test_proxy_host`

Test upstream connectivity for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_regenerate_config`

Regenerate nginx config for a specific proxy host without touching others.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_sync_proxy_hosts`

Sync all proxy host configs and reload nginx.

_No parameters._

#### `npg_clone_proxy_host`

Clone a proxy host with new domain names. Returns the new proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `domain_names` | `array<string>` | ✔ |  |

### SSL / Nginx (8)

#### `npg_list_certificates`

List all SSL/TLS certificates.

_No parameters._

#### `npg_get_certificate`

Get a certificate by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `cert_id` | `string/int` | ✔ |  |

#### `npg_create_certificate`

Request a new Let's Encrypt certificate. Required: domain_names (array), email. Optional: provider (e.g. 'letsencrypt'), dns_provider_id, etc.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `domain_names` | `array<string>` | ✔ |  |
| `email` | `string` | ✔ |  |
| `provider` | `string` | — | `"letsencrypt"` |
| `dns_provider_id` | `string/null` | — | `null` |

#### `npg_delete_certificate`

Delete a certificate by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `cert_id` | `string/int` | ✔ |  |

#### `npg_renew_certificate`

Renew a certificate by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `cert_id` | `string/int` | ✔ |  |

#### `npg_reload_nginx`

Reload nginx configuration without full restart.

_No parameters._

#### `npg_sync_nginx`

Sync all configs and reload nginx.

_No parameters._

#### `npg_test_nginx`

Test nginx configuration for validity.

_No parameters._

### Redirect Hosts (5)

#### `npg_list_redirect_hosts`

List all redirect hosts.

_No parameters._

#### `npg_get_redirect_host`

Get a redirect host by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_create_redirect_host`

Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, default 301).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `domain_names` | `array<string>` | ✔ |  |
| `forward_domain_name` | `string` | ✔ |  |
| `forward_scheme` | `string` | — | `"auto"` |
| `preserve_path` | `bool` | — | `true` |
| `redirect_code` | `int` | — | `301` |

#### `npg_update_redirect_host`

Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `domain_names` | `array<any>/null` | — | `null` |
| `forward_domain_name` | `string/null` | — | `null` |
| `forward_scheme` | `string/null` | — | `null` |
| `preserve_path` | `bool/null` | — | `null` |
| `redirect_code` | `int/null` | — | `null` |

#### `npg_delete_redirect_host`

Delete a redirect host by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

### Security (per-host) (12)

#### `npg_get_proxy_host_rate_limit`

GET rate limit configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_rate_limit`

UPDATE rate limit configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), requests_per_second (int), burst_size (int), zone_size (str), limit_by (str: ip/uri/ip_uri), limit_response (int), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global)

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool/null` | — | `null` |
| `requests_per_second` | `int/null` | — | `null` |
| `burst_size` | `int/null` | — | `null` |
| `zone_size` | `string/null` | — | `null` |
| `limit_by` | `string/null` | — | `null` |
| `limit_response` | `int/null` | — | `null` |
| `disable_global` | `bool/null` | — | `null` |

#### `npg_get_proxy_host_bot_filter`

GET bot filter configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_bot_filter`

UPDATE bot filter configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Required: host_id (str|int). Optional: enabled (bool), block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), custom_blocked_agents (str, comma-separated list), custom_allowed_agents (str, comma-separated list).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool/null` | — | `null` |
| `block_bad_bots` | `bool/null` | — | `null` |
| `block_ai_bots` | `bool/null` | — | `null` |
| `allow_search_engines` | `bool/null` | — | `null` |
| `block_suspicious_clients` | `bool/null` | — | `null` |
| `challenge_suspicious` | `bool/null` | — | `null` |
| `disable_global` | `bool/null` | — | `null` |
| `custom_blocked_agents` | `string/null` | — | `null` |
| `custom_allowed_agents` | `string/null` | — | `null` |

#### `npg_get_proxy_host_security_headers`

GET security headers configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_security_headers`

UPDATE security headers for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), hsts_enabled (bool), hsts_max_age (int), hsts_include_subdomains (bool), hsts_preload (bool), x_frame_options (str: DENY/SAMEORIGIN/''), x_content_type_options (bool), x_xss_protection (bool), referrer_policy (str), content_security_policy (str), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global)

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool/null` | — | `null` |
| `hsts_enabled` | `bool/null` | — | `null` |
| `hsts_max_age` | `int/null` | — | `null` |
| `hsts_include_subdomains` | `bool/null` | — | `null` |
| `hsts_preload` | `bool/null` | — | `null` |
| `x_frame_options` | `string/null` | — | `null` |
| `x_content_type_options` | `bool/null` | — | `null` |
| `x_xss_protection` | `bool/null` | — | `null` |
| `referrer_policy` | `string/null` | — | `null` |
| `content_security_policy` | `string/null` | — | `null` |
| `disable_global` | `bool/null` | — | `null` |

#### `npg_apply_security_header_preset`

APPLY a security header preset to a proxy host. preset: strict, balanced, or relaxed.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `preset` | `string` | ✔ |  |

#### `npg_get_proxy_host_upstream`

GET upstream/load balancing configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_upstream`

UPDATE upstream/load balancing configuration. Body: name, scheme, servers (list of {address, port, weight, backup}), load_balance, health_check_enabled, health_check_path, health_check_interval

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `scheme` | `string` | — | `"http"` |
| `servers` | `array<any>/null` | — | `null` |
| `load_balance` | `string` | — | `"round_robin"` |
| `health_check_enabled` | `bool` | — | `false` |
| `health_check_path` | `string` | — | `"/"` |
| `health_check_interval` | `int` | — | `10` |

#### `npg_get_proxy_host_uri_block`

GET URI block configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_uri_block`

UPDATE URI block configuration. Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `rules` | `array<any>/null` | — | `null` |
| `exception_ips` | `array<any>/null` | — | `null` |
| `allow_private_ips` | `bool` | — | `true` |

#### `npg_get_security_headers_presets`

Get available security header presets.

_No parameters._

### Geo Restriction (5)

#### `npg_get_proxy_host_geo`

GET geo restriction configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_create_proxy_host_geo`

CREATE geo restriction for a proxy host. Required: host_id, countries (list of ISO codes, min 1). Optional: mode (whitelist/blacklist, default blacklist), allowed_ips, challenge_mode, disable_global (bool — false=inherit, true=disable global), allow_private_ips, allow_search_bots

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `countries` | `array<string>` | ✅ | — |
| `mode` | `string` | — | `"blacklist"` |
| `enabled` | `bool` | — | `true` |
| `allowed_ips` | `array<string>/null` | — | `null` |
| `challenge_mode` | `bool` | — | `false` |
| `disable_global` | `bool` | — | `false` |
| `allow_private_ips` | `bool` | — | `true` |
| `allow_search_bots` | `bool` | — | `true` |

#### `npg_update_proxy_host_geo`

UPDATE geo restriction for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode, disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), allow_private_ips, allow_search_bots

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool/null` | — | `null` |
| `mode` | `string/null` | — | `null` |
| `countries` | `array<string>/null` | — | `null` |
| `allowed_ips` | `array<string>/null` | — | `null` |
| `challenge_mode` | `bool/null` | — | `null` |
| `disable_global` | `bool/null` | — | `null` |
| `allow_private_ips` | `bool/null` | — | `null` |
| `allow_search_bots` | `bool/null` | — | `null` |

#### `npg_get_proxy_host_fail2ban`

GET fail2ban configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_fail2ban`

UPDATE fail2ban configuration for a proxy host. Body: enabled, ban_duration, max_retries, etc.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | — | `false` |
| `ban_duration` | `int` | — | `3600` |
| `max_retries` | `int` | — | `5` |

#### `npg_get_proxy_host_challenge`

GET challenge configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_challenge`

UPDATE CAPTCHA/challenge configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), challenge_type (str), site_key (str), token_validity (int), min_score (float), apply_to (str), page_title (str)

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool/null` | — | `null` |
| `challenge_type` | `string/null` | — | `null` |
| `site_key` | `string/null` | — | `null` |
| `token_validity` | `int/null` | — | `null` |
| `min_score` | `float/null` | — | `null` |
| `apply_to` | `string/null` | — | `null` |
| `page_title` | `string/null` | — | `null` |

#### `npg_delete_proxy_host_challenge`

DELETE challenge configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_verify_challenge`

Verify a challenge response. Required: challenge_id, response.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `challenge_id` | `string/int` | ✔ |  |
| `response` | `string` | ✔ |  |

### Access Lists (5)

#### `npg_list_access_lists`

List all access lists (authentication/restriction lists).

_No parameters._

#### `npg_get_access_list`

Get an access list by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `list_id` | `string/int` | ✔ |  |

#### `npg_create_access_list`

Create a new access list. Required: name, advanced_config (block/allow rules).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `advanced_config` | `string` | — | `""` |
| `clients` | `array<any>/null` | — | `null` |

#### `npg_update_access_list`

Update an access list. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `list_id` | `string/int` | ✔ |  |
| `name` | `string/null` | — | `null` |
| `advanced_config` | `string/null` | — | `null` |
| `clients` | `array<any>/null` | — | `null` |

#### `npg_delete_access_list`

Delete an access list by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `list_id` | `string/int` | ✔ |  |

### DNS Providers (6)

#### `npg_list_dns_providers`

List all DNS providers configured for DNS-01 challenges.

_No parameters._

#### `npg_get_dns_provider`

Get a DNS provider by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

#### `npg_create_dns_provider`

Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `provider_type` | `string` | ✔ |  |
| `credentials` | `dict/null` | — | `null` |

#### `npg_update_dns_provider`

Update a DNS provider. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |
| `name` | `string/null` | — | `null` |
| `provider_type` | `string/null` | — | `null` |
| `credentials` | `dict/null` | — | `null` |

#### `npg_delete_dns_provider`

Delete a DNS provider by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

#### `npg_test_dns_provider`

Test DNS provider configuration.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

### Cloud Providers (9)

#### `npg_list_cloud_providers`

List all cloud providers (IP range CIDR databases).

_No parameters._

#### `npg_get_cloud_provider`

Get a cloud provider by its slug.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `slug` | `string` | ✔ |  |

#### `npg_create_cloud_provider`

Create a cloud provider. Required: slug, name, region, cidr_ranges.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `slug` | `string` | ✔ |  |
| `name` | `string` | ✔ |  |
| `region` | `string` | — | `"all"` |
| `cidr_ranges` | `array<string>` | ✔ |  |

#### `npg_update_cloud_provider`

Update a cloud provider. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `slug` | `string` | ✔ |  |
| `name` | `string/null` | — | `null` |
| `region` | `string/null` | — | `null` |
| `cidr_ranges` | `array<string>/null` | — | `null` |

#### `npg_delete_cloud_provider`

Delete a cloud provider by its slug.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `slug` | `string` | ✔ |  |

#### `npg_get_proxy_host_cloud_blocking`

GET cloud provider blocking configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_cloud_blocking`

UPDATE per-host cloud provider blocking (the endpoint full-replaces all fields, so the tool reads current settings and merges — omitted fields are left as-is). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool), cloud_disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `blocked_providers` | `array<string>/null` | — | `null` |
| `challenge_mode` | `bool/null` | — | `null` |
| `allow_search_bots` | `bool/null` | — | `null` |
| `cloud_disable_global` | `bool/null` | — | `null` |

#### `npg_list_cloud_providers_by_region`

List cloud providers filtered by region.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `region` | `string/null` | — | `null` |

### GeoIP (2)

#### `npg_get_geoip_status`

GET GeoIP status and database version.

_No parameters._

#### `npg_update_geoip`

UPDATE GeoIP database. Triggers an update of the GeoIP database.

_No parameters._

### Banned IPs & Bots (4)

#### `npg_ban_ip`

BAN an IP address. Required: ip_address, reason.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `ip_address` | `string` | ✔ |  |
| `reason` | `string` | — | `""` |

#### `npg_unban_ip`

UNBAN an IP address. Required: ip_address.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `ip_address` | `string` | ✔ |  |

#### `npg_get_bots_known`

GET known bot list.

_No parameters._

#### `npg_list_banned_ips`

List banned IPs.

_No parameters._

### URI Block (4)

#### `npg_list_uri_blocks`

List all URI blocks (global and per-host).

_No parameters._

#### `npg_create_uri_block`

Create a URI block for a proxy host. Required: host_id, pattern, action (block/allow). Optional: is_regex.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `pattern` | `string` | ✔ |  |
| `action` | `string` | — | `"block"` |
| `is_regex` | `bool` | — | `false` |

#### `npg_get_uri_block`

Get a URI block by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `block_id` | `string/int` | ✔ |  |

#### `npg_update_uri_block`

Update a URI block. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `block_id` | `string/int` | ✔ |  |
| `pattern` | `string/null` | — | `null` |
| `action` | `string/null` | — | `null` |
| `is_regex` | `bool/null` | — | `null` |

#### `npg_delete_uri_block`

Delete a URI block by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `block_id` | `string/int` | ✔ |  |

### Global URI Block (4)

#### `npg_get_global_uri_block`

GET global URI block configuration.

_No parameters._

#### `npg_update_global_uri_block`

UPDATE global URI block configuration. Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool` | — | `false` |
| `rules` | `array<any>/null` | — | `null` |
| `exception_ips` | `array<string>/null` | — | `null` |
| `allow_private_ips` | `bool` | — | `true` |

#### `npg_add_global_uri_block_rule`

Add a rule to the global URI block. Required: pattern, action. Optional: is_regex.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `pattern` | `string` | ✔ |  |
| `action` | `string` | — | `"block"` |
| `is_regex` | `bool` | — | `false` |

#### `npg_delete_global_uri_block_rule`

Delete a rule from the global URI block by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

### WAF & Exploit Rules (10)

#### `npg_get_waf_hosts`

GET WAF hosts configuration.

_No parameters._

#### `npg_get_waf_host_config`

GET WAF configuration for a specific host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_list_waf_rules`

List all WAF rules.

_No parameters._

#### `npg_get_exploit_rule`

Get an exploit block rule by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

#### `npg_list_exploit_rules`

List all exploit block rules.

_No parameters._

#### `npg_create_exploit_rule`

Create an exploit block rule. Required: name, pattern, action.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `pattern` | `string` | ✔ |  |
| `action` | `string` | — | `"block"` |

#### `npg_update_exploit_rule`

Update an exploit block rule. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |
| `name` | `string/null` | — | `null` |
| `pattern` | `string/null` | — | `null` |
| `action` | `string/null` | — | `null` |

#### `npg_delete_exploit_rule`

Delete an exploit block rule by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

#### `npg_disable_waf_rule`

Disable a WAF rule.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

#### `npg_toggle_exploit_rule`

Toggle an exploit block rule (enable/disable).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

### Settings (4)

#### `npg_get_settings`

Get global NPG settings.

_No parameters._

#### `npg_update_settings`

Update global NPG settings. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `kwargs` | `dict/null` | — | `null` |

#### `npg_get_system_settings`

Get system settings (server name, timezone, locale).

_No parameters._

#### `npg_update_system_settings`

Update system settings. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `kwargs` | `dict/null` | — | `null` |

### Global Settings (7)

#### `npg_get_global_security_headers`

GET global security headers configuration.

_No parameters._

#### `npg_update_global_security_headers`

UPDATE global security headers configuration. Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options, x_content_type_options, x_xss_protection, referrer_policy, content_security_policy.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool` | — | `true` |
| `hsts_enabled` | `bool` | — | `true` |
| `hsts_max_age` | `int` | — | `31536000` |
| `hsts_include_subdomains` | `bool` | — | `true` |
| `hsts_preload` | `bool` | — | `false` |
| `x_frame_options` | `string` | — | `"SAMEORIGIN"` |
| `x_content_type_options` | `bool` | — | `true` |
| `x_xss_protection` | `bool` | — | `true` |
| `referrer_policy` | `string` | — | `"strict-origin-when-cross-origin"` |
| `content_security_policy` | `string` | — | `""` |

#### `npg_get_global_bot_filter`

GET global bot filter configuration.

_No parameters._

#### `npg_update_global_bot_filter`

UPDATE global bot filter configuration. Body: enabled, block_bad_bots, block_ai_bots, allow_search_engines, block_suspicious_clients, challenge_suspicious, custom_blocked_agents, custom_allowed_agents.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool` | — | `false` |
| `block_bad_bots` | `bool` | — | `true` |
| `block_ai_bots` | `bool` | — | `false` |
| `allow_search_engines` | `bool` | — | `true` |
| `block_suspicious_clients` | `bool` | — | `false` |
| `challenge_suspicious` | `bool` | — | `false` |
| `custom_blocked_agents` | `string/null` | — | `null` |
| `custom_allowed_agents` | `string/null` | — | `null` |

#### `npg_get_global_cloud_providers`

GET global cloud providers configuration.

_No parameters._

#### `npg_update_global_cloud_providers`

UPDATE global cloud providers configuration (full replace — all 3 fields are written; the global default is the singleton inherited by hosts without their own override). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `blocked_providers` | `array<string>/null` | — | `null` |
| `challenge_mode` | `bool` | — | `false` |
| `allow_search_bots` | `bool` | — | `false` |

#### `npg_get_global_geo`

GET global GeoIP restriction configuration.

_No parameters._

#### `npg_update_global_geo`

UPDATE global GeoIP restriction configuration (partial update — only provided fields are changed; omitted fields are left as-is. The global default is inherited by hosts without their own override). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, allow_private_ips, allow_search_bots, challenge_mode

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool/null` | — | `null` |
| `mode` | `string/null` | — | `null` |
| `countries` | `array<string>/null` | — | `null` |
| `allowed_ips` | `array<string>/null` | — | `null` |
| `allow_private_ips` | `bool/null` | — | `null` |
| `allow_search_bots` | `bool/null` | — | `null` |
| `challenge_mode` | `bool/null` | — | `null` |

#### `npg_get_global_rate_limit`

GET global rate limit configuration.

_No parameters._

#### `npg_update_global_rate_limit`

UPDATE global rate limit configuration. Body: enabled, requests_per_second, burst_size, zone_size, limit_by, limit_response.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool` | — | `false` |
| `requests_per_second` | `int` | — | `10` |
| `burst_size` | `int` | — | `20` |
| `zone_size` | `string` | — | `"10m"` |
| `limit_by` | `string` | — | `"ip"` |
| `limit_response` | `int` | — | `429` |

#### `npg_get_global_waf`

GET global WAF configuration.

_No parameters._

#### `npg_update_global_waf`

UPDATE global WAF configuration. Body: enabled, paranoia_level, anomaly_threshold, rules (list of {id, enabled}).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `enabled` | `bool` | — | `false` |
| `paranoia_level` | `int` | — | `1` |
| `anomaly_threshold` | `int` | — | `5` |
| `rules` | `array<any>/null` | — | `null` |

### Logs (10)

#### `npg_get_logs`

Get access logs.

_No parameters._

#### `npg_get_log_settings`

Get log settings.

_No parameters._

#### `npg_update_log_settings`

Update log settings. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `kwargs` | `dict/null` | — | `null` |

#### `npg_get_log_stats`

Get log statistics.

_No parameters._

#### `npg_list_audit_logs`

List audit log entries.

_No parameters._

#### `npg_list_system_logs`

List system logs.

_No parameters._

#### `npg_list_log_files`

List all log files.

_No parameters._

#### `npg_get_log_file`

Get a log file by its filename.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `filename` | `string` | ✔ |  |

#### `npg_download_log_file`

Download a log file by its filename.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `filename` | `string` | ✔ |  |

#### `npg_view_log_file`

View the contents of a log file.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `filename` | `string` | ✔ |  |
| `lines` | `int` | — | `100` |

#### `npg_rotate_log_file`

Rotate a log file by its filename.

_No parameters._

#### `npg_delete_log_file`

Delete a log file by its filename.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `filename` | `string` | ✔ |  |

### Backups (8)

#### `npg_list_backups`

List all backups.

_No parameters._

#### `npg_get_backup`

Get a backup by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `backup_id` | `string/int` | ✔ |  |

#### `npg_create_backup`

Create a new backup.

_No parameters._

#### `npg_delete_backup`

Delete a backup by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `backup_id` | `string/int` | ✔ |  |

#### `npg_restore_backup`

Restore from a backup. Required: backup_id.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `backup_id` | `string/int` | ✔ |  |

#### `npg_download_backup`

Download a backup by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `backup_id` | `string/int` | ✔ |  |

#### `npg_upload_restore_backup`

Upload and restore from a backup file.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `file_content` | `string` | ✔ |  |

#### `npg_get_backup_stats`

Get backup statistics.

_No parameters._

### API Tokens (6)

#### `npg_list_api_tokens`

List all API tokens.

_No parameters._

#### `npg_get_api_token`

Get an API token by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `token_id` | `string/int` | ✔ |  |

#### `npg_create_api_token`

Create a new API token. Required: name, permissions (array). Optional: expires_at.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `permissions` | `array<string>` | ✔ |  |
| `expires_at` | `string/null` | — | `null` |

#### `npg_update_api_token`

Update an API token. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `token_id` | `string/int` | ✔ |  |
| `kwargs` | `dict/null` | — | `null` |

#### `npg_revoke_api_token`

Revoke an API token by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `token_id` | `string/int` | ✔ |  |

#### `npg_delete_api_token`

Delete an API token by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `token_id` | `string/int` | ✔ |  |

### Users (8)

#### `npg_list_users`

List all users.

_No parameters._

#### `npg_get_user`

Get a user by their ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `user_id` | `string/int` | ✔ |  |

#### `npg_create_user`

Create a new user. Required: username, email, password. Optional: role_id, is_active.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `username` | `string` | ✔ |  |
| `email` | `string` | ✔ |  |
| `password` | `string` | ✔ |  |
| `role_id` | `str/int/null` | — | `null` |
| `is_active` | `bool` | — | `true` |

#### `npg_set_user_password`

Set/reset a user's password. Required: user_id, new_password.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `user_id` | `string/int` | ✔ |  |
| `new_password` | `string` | ✔ |  |

#### `npg_assign_user_role`

Assign a role to a user. Required: user_id, role_id.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `user_id` | `string/int` | ✔ |  |
| `role_id` | `str/int` | ✔ |  |

#### `npg_end_user_sessions`

End all sessions for a user (force logout). Required: user_id.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `user_id` | `string/int` | ✔ |  |

#### `npg_delete_user`

Delete a user by their ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `user_id` | `string/int` | ✔ |  |

### Roles (5)

#### `npg_list_roles`

List all roles.

_No parameters._

#### `npg_get_role`

Get a role by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `role_id` | `string/int` | ✔ |  |

#### `npg_create_role`

Create a new role. Required: name, permissions (array of permission strings).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `permissions` | `array<string>` | ✔ |  |

#### `npg_update_role`

Update a role. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `role_id` | `string/int` | ✔ |  |
| `name` | `string/null` | — | `null` |
| `permissions` | `array<string>/null` | — | `null` |

#### `npg_delete_role`

Delete a role by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `role_id` | `string/int` | ✔ |  |

### SSO Providers (6)

#### `npg_list_sso_providers`

List all SSO providers.

_No parameters._

#### `npg_get_sso_provider`

Get an SSO provider by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

#### `npg_create_sso_provider`

Create a new SSO provider. Required: name, provider_type (e.g. 'google', 'github', 'oidc'). Optional: config (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `provider_type` | `string` | ✔ |  |
| `config` | `dict/null` | — | `null` |

#### `npg_update_sso_provider`

Update an SSO provider. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |
| `name` | `string/null` | — | `null` |
| `provider_type` | `string/null` | — | `null` |
| `config` | `dict/null` | — | `null` |

#### `npg_delete_sso_provider`

Delete an SSO provider by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

#### `npg_test_sso_provider`

Test SSO provider configuration by initiating a test login flow.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

### Notification Channels (8)

#### `npg_list_notification_channels`

List all notification channels.

_No parameters._

#### `npg_get_notification_channel`

Get a notification channel by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `channel_id` | `string/int` | ✔ |  |

#### `npg_create_notification_channel`

Create a notification channel. Required: name, type (e.g. 'email', 'telegram', 'slack'). Optional: config (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `channel_type` | `string` | ✔ |  |
| `config` | `dict/null` | — | `null` |

#### `npg_update_notification_channel`

Update a notification channel. Pass only fields to change.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `channel_id` | `string/int` | ✔ |  |
| `name` | `string/null` | — | `null` |
| `channel_type` | `string/null` | — | `null` |
| `config` | `dict/null` | — | `null` |

#### `npg_delete_notification_channel`

Delete a notification channel by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `channel_id` | `string/int` | ✔ |  |

#### `npg_test_notification_channel`

Test a notification channel by sending a test message.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `channel_id` | `string/int` | ✔ |  |

#### `npg_get_notification_deliveries`

Get delivery history for a notification channel.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `channel_id` | `string/int` | ✔ |  |

#### `npg_detect_telegram_chats`

Detect available Telegram chats for notification delivery.

_No parameters._

### Catalog (2)

#### `npg_get_catalog`

Get the exploit block rule catalog.

_No parameters._

#### `npg_subscribe_catalog`

Subscribe to a catalog entry. Required: catalog_id.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `catalog_id` | `string/int` | ✔ |  |

### Docker (2)

#### `npg_get_docker_containers`

Get status of all Docker containers managed by NPG.

_No parameters._

#### `npg_get_upstream_health`

GET health status of an upstream server.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `upstream_id` | `string/int` | ✔ |  |

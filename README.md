# NPG MCP Server

**English** | [한국어](README.ko.md)

MCP server for [NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard) (NPG) — manage proxy hosts, certificates, SSL, security rules, and nginx configuration through MCP tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org/).

> **⚠️ Vibe-coded with an AI agent.** This codebase was generated at speed by an AI agent, not hand-crafted by a human. Expect rough edges, unhandled edge cases, and bugs. Do **not** deploy it to an active/production NginxProxyGuard instance without first testing against a **sandboxed / disposable NPG environment** and reviewing the code. It can create, update, delete, and reconfigure live proxy hosts, so verify in isolation before pointing it at real infrastructure.

## Tools Reference

The server exposes **108 MCP tools**. Each tool is documented below with a short description and its **input parameter schema** (parameter, type, whether it is required, and default value). Tools are grouped into the following categories:

- **Auth** — 4 tools
- **Dashboard** — 3 tools
- **Proxy Hosts** — 10 tools
- **SSL / Nginx** — 8 tools
- **Redirect Hosts** — 5 tools
- **Security (per-host)** — 12 tools
- **Geo Restriction** — 5 tools
- **Fail2ban & Challenge** — 6 tools
- **Access Lists** — 5 tools
- **DNS Providers** — 6 tools
- **Cloud Providers** — 5 tools
- **GeoIP** — 2 tools
- **Banned IPs & Bots** — 4 tools
- **URI Block** — 2 tools
- **WAF & Exploit Rules** — 10 tools
- **Settings** — 4 tools
- **Logs** — 6 tools
- **Backups** — 5 tools
- **API Tokens** — 6 tools

### Auth (4)

#### `npg_auth_login`

Authenticate with NPG credentials. The resulting session token is stored server-side; it is not returned to the client.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `username` | `string` | ✔ |  |
| `password` | `string` | ✔ |  |
| `tfa_code` | `string/null` | — | `null` |

#### `npg_auth_logout`

Invalidate the current session token.

_No parameters._

#### `npg_auth_me`

Get the current authenticated user's info.

_No parameters._

#### `npg_change_password`

Change the current user's password. REQUIRED: current_password, new_password (min 8 chars).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `current_password` | `string` | ✔ |  |
| `new_password` | `string` | ✔ |  |

### Dashboard (3)

#### `npg_get_dashboard`

Get dashboard data (summary of proxy hosts, certificates, etc.).

_No parameters._

#### `npg_get_dashboard_health`

Get system health status.

_No parameters._

#### `npg_get_dashboard_geoip_stats`

GET GeoIP statistics by country for the dashboard.

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

Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: forward_scheme, block_normal, waf_enabled, block_http, ssl_forced, ssl_cert_id, cache_enabled, etc.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `domain_names` | `array<string>` | ✔ |  |
| `forward_host` | `string` | ✔ |  |
| `forward_port` | `int` | ✔ |  |
| `forward_scheme` | `string` | — | `"http"` |
| `block_normal` | `bool` | — | `false` |
| `waf_enabled` | `bool` | — | `false` |
| `block_http` | `bool` | — | `false` |
| `ssl_enabled` | `bool` | — | `true` |
| `ssl_forced` | `bool` | — | `true` |
| `ssl_cert_id` | `string/int/null` | — | `null` |
| `cache_enabled` | `bool` | — | `false` |
| `cache_template` | `string` | — | `"ignore"` |
| `advanced_config` | `string` | — | `""` |
| `enable_proxy_headers` | `bool` | — | `true` |
| `host_header` | `string/null` | — | `null` |
| `extra_domains` | `array<any>/null` | — | `null` |
| `block_exploits` | `bool` | — | `false` |

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

UPDATE rate limit configuration for a proxy host. Body: enabled, requests_per_second, burst_size, zone_size, limit_by (ip/uri/ip_uri), limit_response

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `requests_per_second` | `int` | ✔ |  |
| `burst_size` | `int` | ✔ |  |
| `zone_size` | `string` | — | `"10m"` |
| `limit_by` | `string` | — | `"ip"` |
| `limit_response` | `int` | — | `429` |

#### `npg_get_proxy_host_bot_filter`

GET bot filter configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_bot_filter`

UPDATE bot filter configuration for a proxy host. Required: host_id (str\|int), enabled (bool). Optional: block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool), custom_blocked_agents (str, comma-separated list).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `block_bad_bots` | `bool` | — | `true` |
| `block_ai_bots` | `bool` | — | `false` |
| `allow_search_engines` | `bool` | — | `true` |
| `block_suspicious_clients` | `bool` | — | `false` |
| `challenge_suspicious` | `bool` | — | `false` |
| `disable_global` | `bool` | — | `false` |
| `custom_blocked_agents` | `string/null` | — | `null` |

#### `npg_get_proxy_host_security_headers`

GET security headers configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_security_headers`

UPDATE security headers for a proxy host. Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options (DENY/SAMEORIGIN/''), x_content_type_options, x_xss_protection, referrer_policy, content_security_policy

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `hsts_enabled` | `bool` | — | `true` |
| `hsts_max_age` | `int` | — | `31536000` |
| `hsts_include_subdomains` | `bool` | — | `true` |
| `hsts_preload` | `bool` | — | `false` |
| `x_frame_options` | `string` | — | `"SAMEORIGIN"` |
| `x_content_type_options` | `bool` | — | `true` |
| `x_xss_protection` | `bool` | — | `true` |
| `referrer_policy` | `string` | — | `"strict-origin-when-cross-origin"` |
| `content_security_policy` | `string` | — | `""` |

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

CREATE geo restriction for a proxy host. Body: enabled, mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `mode` | `string` | — | `"blacklist"` |
| `countries` | `array<any>/null` | — | `null` |
| `allowed_ips` | `array<any>/null` | — | `null` |
| `challenge_mode` | `bool` | — | `false` |

#### `npg_update_proxy_host_geo`

UPDATE geo restriction for a proxy host. Body: enabled, mode, countries, allowed_ips, challenge_mode

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `mode` | `string` | — | `"blacklist"` |
| `countries` | `array<any>/null` | — | `null` |
| `allowed_ips` | `array<any>/null` | — | `null` |
| `challenge_mode` | `bool` | — | `false` |

#### `npg_delete_proxy_host_geo`

DELETE geo restriction for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_list_countries`

List available country codes for GeoIP blocking.

_No parameters._

### Fail2ban & Challenge (6)

#### `npg_get_proxy_host_fail2ban`

GET fail2ban configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_fail2ban`

UPDATE fail2ban configuration. Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge)

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `max_retries` | `int` | — | `5` |
| `find_time` | `int` | — | `600` |
| `ban_time` | `int` | — | `3600` |
| `fail_codes` | `string` | — | `"401,403"` |
| `action` | `string` | — | `"block"` |

#### `npg_get_proxy_host_challenge`

GET CAPTCHA/challenge configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_update_proxy_host_challenge`

UPDATE CAPTCHA/challenge configuration. Body: enabled, challenge_type (captcha/js_challenge), difficulty, site_key, token_validity, min_score, apply_to, page_title, challenge_ips

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `challenge_type` | `string` | — | `"captcha"` |
| `difficulty` | `string` | — | `"medium"` |
| `site_key` | `string` | — | `""` |
| `token_validity` | `int` | — | `86400` |
| `min_score` | `number` | — | `0.5` |
| `apply_to` | `string` | — | `"both"` |
| `page_title` | `string` | — | `"Security Check"` |

#### `npg_delete_proxy_host_challenge`

DELETE CAPTCHA/challenge configuration for a proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_verify_challenge`

Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `token` | `string` | ✔ |  |
| `solution` | `string` | ✔ |  |

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
| `credentials` | `object/null` | — | `null` |
| `kwargs` | `object/null` | — | `null` |

#### `npg_update_dns_provider`

Update a DNS provider. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |
| `kwargs` | `object/null` | — | `null` |

#### `npg_delete_dns_provider`

Delete a DNS provider by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

#### `npg_test_dns_provider`

Test DNS provider credentials.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `provider_id` | `string/int` | ✔ |  |

### Cloud Providers (5)

#### `npg_list_cloud_providers`

List all cloud providers (for certificate DNS challenges).

_No parameters._

#### `npg_get_cloud_provider`

Get a cloud provider by its slug.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `slug` | `string` | ✔ |  |

#### `npg_create_cloud_provider`

Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `name` | `string` | ✔ |  |
| `slug` | `string` | ✔ |  |
| `ip_ranges` | `array<string>` | ✔ |  |
| `region` | `string/null` | — | `null` |
| `description` | `string/null` | — | `null` |
| `kwargs` | `object/null` | — | `null` |

#### `npg_update_cloud_provider`

Update a cloud provider by its slug. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `slug` | `string` | ✔ |  |
| `kwargs` | `object/null` | — | `null` |

#### `npg_delete_cloud_provider`

Delete a cloud provider by its slug.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `slug` | `string` | ✔ |  |

### GeoIP (2)

#### `npg_get_geoip_status`

Get GeoIP database update status.

_No parameters._

#### `npg_update_geoip`

Update GeoIP databases.

_No parameters._

### Banned IPs & Bots (4)

#### `npg_list_banned_ips`

List banned IP addresses.

_No parameters._

#### `npg_ban_ip`

Ban an IP address. Required: ip. Optional: ban_time (seconds).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `ip_address` | `string` | ✔ |  |
| `reason` | `string` | — | `"Manual ban via API"` |
| `duration` | `int` | — | `3600` |

#### `npg_unban_ip`

Unban an IP by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `ip_id` | `string/int` | ✔ |  |

#### `npg_get_bots_known`

Get list of known bot user-agent signatures.

_No parameters._

### URI Block (2)

#### `npg_get_global_uri_block`

Get global URI block settings.

_No parameters._

#### `npg_update_global_uri_block`

Update global URI block settings. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `kwargs` | `object/null` | — | `null` |

### WAF & Exploit Rules (10)

#### `npg_list_exploit_rules`

List exploit block rules.

_No parameters._

#### `npg_get_exploit_rule`

Get an exploit rule by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

#### `npg_create_exploit_rule`

Create an exploit block rule. Required: category, name, pattern, pattern_type (e.g. 'query_string'). Optional: severity, description.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `category` | `string` | ✔ |  |
| `name` | `string` | ✔ |  |
| `pattern` | `string` | ✔ |  |
| `pattern_type` | `string` | ✔ |  |
| `severity` | `string/null` | — | `null` |
| `description` | `string/null` | — | `null` |
| `kwargs` | `object/null` | — | `null` |

#### `npg_update_exploit_rule`

Update an exploit rule. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |
| `kwargs` | `object/null` | — | `null` |

#### `npg_delete_exploit_rule`

Delete an exploit rule by its ID.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

#### `npg_toggle_exploit_rule`

Toggle an exploit rule's enabled status.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `rule_id` | `string/int` | ✔ |  |

#### `npg_list_waf_rules`

List all WAF (Web Application Firewall) rules.

_No parameters._

#### `npg_get_waf_hosts`

Get WAF config for all proxy hosts.

_No parameters._

#### `npg_get_waf_host_config`

Get WAF config for a specific proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |

#### `npg_disable_waf_rule`

Disable a WAF rule for a specific proxy host.

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `host_id` | `string/int` | ✔ |  |
| `rule_id` | `string/int` | ✔ |  |

### Settings (4)

#### `npg_get_settings`

Get global NPG settings.

_No parameters._

#### `npg_update_settings`

Update global NPG settings. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `kwargs` | `object/null` | — | `null` |

#### `npg_get_system_settings`

Get system settings (server name, timezone, locale).

_No parameters._

#### `npg_update_system_settings`

Update system settings. Pass only fields to change (dict).

| Param | Type | Required | Default |
|-------|------|:---:|--------|
| `kwargs` | `object/null` | — | `null` |

### Logs (6)

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
| `kwargs` | `object/null` | — | `null` |

#### `npg_get_log_stats`

Get log statistics.

_No parameters._

#### `npg_list_audit_logs`

List audit log entries.

_No parameters._

#### `npg_list_system_logs`

List system logs.

_No parameters._

### Backups (5)

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
| `kwargs` | `object/null` | — | `null` |

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

## Quick Start

### Prerequisites

- A running NginxProxyGuard (NPG) instance with API access
- Docker and Docker Compose (for containerized deployment)
- Python 3.11+ (for local development)

### Local Development

```bash
git clone https://github.com/four2mis/npg-mcp.git
cd npg-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create a `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
```

Run in stdio mode:

```bash
python3 -m npg_mcp.main
```

### Docker Deployment (pre-built)

Pull the image from GitHub Container Registry:

```bash
docker pull ghcr.io/four2mis/npg-mcp:latest
```

Create a `.env` file from the template:

```bash
cp .env.example .env
# then edit .env with your NPG credentials
```

Or run with Docker Compose using the included `docker-compose.yml`:

```bash
# Pull & run (uses pre-built image)
docker compose up -d

# Or build from source
docker compose up -d --build
```

The included `docker-compose.yml`:

```yaml
services:
  npg-mcp:
    image: ghcr.io/four2mis/npg-mcp:latest
    # build: .  # uncomment to build from source instead
    container_name: npg-mcp
    restart: unless-stopped
    networks:
      - npg-network
    # All runtime config comes from .env (see .env.example). No secrets here.
    env_file:
      - .env
    ports:
      - "8081:8081"

networks:
  npg-network:
    external: true
```

## Connecting to MCP Clients

Deploying the server (Docker section above) publishes the MCP endpoint at `http://<host>:8081/mcp`. Add it to any MCP-capable agent by pointing at that URL.

> **If `MCP_API_TOKEN` is set (recommended for any network-exposed deployment), every MCP request MUST carry the `Authorization: Bearer <MCP_API_TOKEN>` header** — requests without it get `401`. Every client config below shows where the header goes. The token (`openssl rand -hex 32`) is set in the server's `.env` as `MCP_API_TOKEN`.

### Hermes Agent

Add to `~/.hermes/config.yaml` under `mcp_servers`, then restart Hermes (MCP servers are discovered at startup; no hot-reload):

```yaml
mcp_servers:
  npg-mcp:
    url: http://<host>:8081/mcp
    connect_timeout: 30
    headers:
      Authorization: "Bearer <MCP_API_TOKEN>"
```

Or set it with the CLI instead of hand-editing the config:

```bash
hermes config set mcp_servers.npg-mcp.url 'http://<host>:8081/mcp'
hermes config set mcp_servers.npg-mcp.headers.Authorization 'Bearer <MCP_API_TOKEN>'
```

Tools then appear as `mcp_npg_mcp_*` (e.g. `mcp_npg_mcp_npg_list_proxy_hosts`).

### Claude Code / Claude Desktop

Add to your Claude MCP settings (Claude Desktop: `claude_desktop_config.json`);
Claude Code: `~/.claude.json` — `mcpServers` key, or `claude mcp add`):

```json
{
  "mcpServers": {
    "npg-mcp": {
      "url": "http://<host>:8081/mcp",
      "headers": { "Authorization": "Bearer <MCP_API_TOKEN>" }
    }
  }
}
```

### OpenAI Codex CLI

Add to `~/.codex/config.toml` under `[mcp_servers.npg-mcp]`:

```toml
[mcp_servers.npg-mcp]
url = "http://<host>:8081/mcp"
headers = { Authorization = "Bearer <MCP_API_TOKEN>" }
```

### Cursor / VS Code / Other MCP Clients

Add a **remote / SSE+HTTP MCP server** entry in the client's MCP settings with:

- **URL:** `http://<host>:8081/mcp`
- **Headers:** `Authorization: Bearer <MCP_API_TOKEN>` (if a token is configured)

Any MCP client that supports Streamable HTTP servers (`type: "http"` / `sse`) can connect. The endpoint is a standard FastMCP Streamable HTTP server.

### Network & Firewall Notes

- The server listens on `MCP_PORT` (default `8081`) bound to `MCP_HOST` (default `0.0.0.0`).
- **DNS-rebinding protection** (`MCP_REBINDING_PROTECTION=true` by default) rejects requests whose `Host` header isn't in `MCP_ALLOWED_HOSTS`. If clients connect by hostname/IP not covered by the default (`localhost:8081,127.0.0.1:8081`), add it to `MCP_ALLOWED_HOSTS` in `.env`, e.g. `MCP_ALLOWED_HOSTS=127.0.0.1:8081,mynas.local:8081,192.168.1.50:8081`.
- **Security first:** only expose the MCP endpoint to trusted networks. If you must expose it publicly, set `MCP_API_TOKEN` and keep `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS` scoped (README §Environment Variables).

## Authentication

The server **auto-authenticates** on first use using `NPG_USERNAME` and `NPG_PASSWORD`. No manual token management needed — every tool call automatically refreshes auth.

Alternatively, call `npg_auth_login` directly for explicit authentication. The resulting NPG session token is stored **server-side only** and is never returned to the client.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NPG_BASE_URL` | `http://npg-api:8080` | NPG API base URL |
| `NPG_USERNAME` | — | NPG login username (required) |
| `NPG_PASSWORD` | — | NPG login password (required) |
| `MCP_PORT` | `8081` | MCP server listening port |
| `MCP_HOST` | `0.0.0.0` | MCP server bind host |
| `MCP_API_TOKEN` | *(empty)* | Bearer token required on the MCP endpoint. **Leave empty for open (local/LAN-only) mode.** Generate with `openssl rand -hex 32`. |
| `MCP_ALLOWED_HOSTS` | `localhost:port` | Comma-separated `host:port` whose `Host` header the endpoint accepts (e.g. your reverse-proxy public host) |
| `MCP_ALLOWED_ORIGINS` | *(empty)* | Comma-separated origins accepted for cross-origin requests; restricts CSRF |
| `MCP_REBINDING_PROTECTION` | `true` | Enable DNS-rebinding protection (disable only if it breaks your proxy) |

## Project Structure

```
npg_mcp/
  main.py       # All 108+ MCP tools
  client.py     # HTTP client wrapper with auto-auth
  __init__.py
Dockerfile      # Multi-stage Docker build
docker-compose.yml
pyproject.toml  # Dependencies: mcp>=1.0, httpx>=0.27
```

## License

MIT
# NPG MCP Server

**English** | [한국어](README.ko.md)

MCP server for [NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard) (NPG) — manage proxy hosts, certificates, SSL, security rules, and nginx configuration through MCP tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org/).

> **⚠️ Vibe-coded with an AI agent.** This codebase was generated at speed by an AI agent, not hand-crafted by a human. Expect rough edges, unhandled edge cases, and bugs. Do **not** deploy it to an active/production NginxProxyGuard instance without first testing against a **sandboxed / disposable NPG environment** and reviewing the code. It can create, update, delete, and reconfigure live proxy hosts, so verify in isolation before pointing it at real infrastructure.

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

> **If `MCP_API_TOKEN` is set (recommended for any network-exposed deployment), every MCP request MUST carry the `Authorization: Bearer *** header** — requests without it get `401`. Every client config below shows where the header goes. The token (`openssl rand -hex 32`) is set in the server's `.env` as `MCP_API_TOKEN`.

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
- **Headers:** `Authorization: Bearer *** (if a token is configured)

Any MCP client that supports Streamable HTTP servers (`type: "http"` / `sse`) can connect. The endpoint is a standard FastMCP Streamable HTTP server.

### Network & Firewall Notes

- The server listens on `MCP_PORT` (default `8081`) bound to `MCP_HOST` (default `0.0.0.0`).
- **DNS-rebinding protection** (`MCP_REBINDING_PROTECTION=true` by default) rejects requests whose `Host` header isn't in `MCP_ALLOWED_HOSTS`. If clients connect by hostname/IP not covered by the default (`localhost:8081,127.0.0.1:8081`), add it to `MCP_ALLOWED_HOSTS` in `.env`, e.g. `MCP_ALLOWED_HOSTS=127.0.0.1:8081,mynas.local:8081,192.168.1.50:8081`.
- **Security first:** only expose the MCP endpoint to trusted networks. If you must expose it publicly, set `MCP_API_TOKEN` and keep `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS` scoped (see §Environment Variables).

## Tools Reference

This server exposes **286 MCP tools** across 28 categories. Each category lists its tools with a brief description; full input parameter schemas are in [`tool-schemas.yaml`](tool-schemas.yaml).

| Category | Tools |
|----------|-------|
| **Proxy Hosts** | 34 tools |
| **Logs** | 32 tools |
| **Security & WAF** | 27 tools |
| **DNS Providers** | 15 tools |
| **Authentication** | 18 tools |
| **Certificates** | 15 tools |
| **Filter Subscriptions** | 15 tools |
| **Cloud Providers** | 13 tools |
| **URI Block** | 10 tools |
| **Settings** | 11 tools |
| **Backups** | 8 tools |
| **API Tokens** | 8 tools |
| **Users** | 9 tools |
| **SSO Providers** | 7 tools |
| **Dashboard** | 3 tools |
| **IP Management** | 4 tools |
| **Notification Channels** | 8 tools |
| **Redirect Hosts** | 6 tools |
| **Access Lists** | 5 tools |
| **Geo** | 10 tools |
| **Fail2ban & Challenge** | 3 tools |
| **Banned IPs & Bots** | 5 tools |
| **Roles** | 4 tools |
| **System** | 11 tools |
| **SSL / Nginx** | 3 tools |
| **System & Health** | 1 tool |
| **Docker** | 1 tool |

### Proxy Hosts (34)

| Tool | Description |
|------|-------------|
| `npg_list_proxy_hosts` | List all proxy hosts. Returns a list of proxy host objects. |
| `npg_get_proxy_host` | Get a single proxy host by its ID. |
| `npg_get_proxy_host_by_domain` | Get a proxy host by its domain name. |
| `npg_create_proxy_host` | Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: pass only the fields you want to change; omitted fields inherit global defaults or sensible built-in defaults. Fields: proxy_type (default 'http'), forward_scheme (default 'http'), enabled (default True), ssl_enabled, ssl_forced (default True), ssl_http2 (default True), ssl_http3, ssl_cert_id, waf_enabled, waf_use_global (default True), waf_paranoia_level, waf_anomaly_threshold, waf_mode, cache_enabled, cache_static_only, cache_ttl, cache_template, block_normal, block_http, block_exploits (default True), block_exploits_exceptions, allow_websocket_upgrade (default True), enable_proxy_headers, host_header, extra_domains, advanced_config, proxy_buffering (str), proxy_request_buffering (str), client_max_body_size (str), proxy_max_temp_file_size (str), proxy_connect/send/read_timeout, access_list_id, auth_provider_id, auth_bypass_paths, ddns_enabled/provider_id/proxied, forward_container_name/network, stream_* fields. |
| `npg_update_proxy_host` | Update an existing proxy host (partial update — pass only the fields you want to change; omitted fields are left as-is). Use `skip_nginx=true` to skip nginx regeneration. Fields: domain_names, forward_host, forward_port, forward_scheme, block_normal, waf_enabled, waf_use_global (bool \| None — tri-state: omit=leave unchanged, false=host own WAF config, true=inherit global WAF), waf_paranoia_level, waf_anomaly_threshold, block_http, ssl_forced, ssl_cert_id, cache_enabled, cache_static_only, cache_ttl (str), cache_template, advanced_config, enable_proxy_headers, host_header, extra_domains, enabled, ssl_http2, ssl_http3, block_exploits, block_exploits_exceptions, allow_websocket_upgrade, proxy_connect/send/read_timeout, proxy_buffering (str: 'on'/'off'/''), proxy_request_buffering (str: 'on'/'off'/''), client_max_body_size (str, e.g. '10m'/'off'), proxy_max_temp_file_size (str), access_list_id, auth_provider_id, auth_bypass_paths (list[str]), ddns_enabled/provider_id/proxied, forward_container_name/network. Nullable id fields (certificate_id, access_list_id, auth_provider_id, ddns_provider_id, forward_container_name/network): empty string clears, omitted leaves unchanged; auth_bypass_paths: [] clears. |
| `npg_delete_proxy_host` | Delete a proxy host by its ID. |
| `npg_test_proxy_host` | Test upstream connectivity for a proxy host. |
| `npg_regenerate_config` | Regenerate nginx config for a specific proxy host without touching others. |
| `npg_sync_proxy_hosts` | Sync all proxy host configs and reload nginx. |
| `npg_clone_proxy_host` | Clone a proxy host with new domain names. Returns the new proxy host. |
| `npg_get_proxy_host_rate_limit` | GET rate limit configuration for a proxy host. |
| `npg_update_proxy_host_rate_limit` | UPDATE rate limit configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), requests_per_second (int), burst_size (int), zone_size (str), limit_by (str: ip/uri/ip_uri), limit_response (int), disable_global (bool \| None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global) |
| `npg_get_proxy_host_bot_filter` | GET bot filter configuration for a proxy host. |
| `npg_update_proxy_host_bot_filter` | UPDATE bot filter configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Required: host_id (str\|int). Optional: enabled (bool), block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool \| None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), custom_blocked_agents (str, comma-separated list), custom_allowed_agents (str, comma-separated list). |
| `npg_get_proxy_host_security_headers` | GET security headers configuration for a proxy host. |
| `npg_update_proxy_host_security_headers` | UPDATE security headers for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), hsts_enabled (bool), hsts_max_age (int), hsts_include_subdomains (bool), hsts_preload (bool), x_frame_options (str: DENY/SAMEORIGIN/''), x_content_type_options (bool), x_xss_protection (bool), referrer_policy (str), content_security_policy (str), disable_global (bool \| None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global) |
| `npg_apply_security_header_preset` | APPLY a security header preset to a proxy host. preset: strict, balanced, or relaxed. |
| `npg_get_proxy_host_upstream` | GET upstream/load balancing configuration for a proxy host. |
| `npg_update_proxy_host_upstream` | UPDATE upstream/load balancing configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: scheme, servers (list of {address, port, weight, backup}), load_balance, health_check_enabled, health_check_path, health_check_interval. |
| `npg_get_proxy_host_uri_block` | GET URI block configuration for a proxy host. |
| `npg_update_proxy_host_uri_block` | UPDATE URI block configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips. |
| `npg_get_proxy_host_fail2ban` | GET fail2ban configuration for a proxy host. |
| `npg_update_proxy_host_fail2ban` | UPDATE fail2ban configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge). |
| `npg_get_proxy_host_challenge` | GET CAPTCHA/challenge configuration for a proxy host. |
| `npg_update_proxy_host_challenge` | UPDATE CAPTCHA/challenge configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), challenge_type (str), site_key (str), token_validity (int), min_score (float), apply_to (str), page_title (str) |
| `npg_delete_proxy_host_challenge` | DELETE CAPTCHA/challenge configuration for a proxy host. |
| `npg_verify_challenge` | Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution. |
| `npg_set_proxy_host_favorite` | Toggle a proxy host as a favorite. REQUIRED: host_id, favorite (bool). |
| `npg_delete_proxy_host_rate_limit` | Delete the rate limit config for a proxy host — host falls back to global default. REQUIRED: host_id. |
| `npg_delete_proxy_host_bot_filter` | Delete the bot filter config for a proxy host — host falls back to global default. REQUIRED: host_id. |
| `npg_delete_proxy_host_security_headers` | Delete the security headers config for a proxy host — host falls back to global default. REQUIRED: host_id. |
| `npg_delete_proxy_host_upstream` | Delete the upstream/load balancing config for a proxy host — host falls back to defaults. REQUIRED: host_id. |
| `npg_delete_proxy_host_uri_block` | Delete the URI block config for a proxy host — host falls back to global default. REQUIRED: host_id. |
| `npg_delete_proxy_host_fail2ban` | Delete the fail2ban config for a proxy host — host falls back to global default. REQUIRED: host_id. |

### Logs (32)

| Tool | Description |
|------|-------------|
| `npg_get_logs` | Get access logs. |
| `npg_get_log_settings` | Get log settings. |
| `npg_update_log_settings` | Update log settings. Pass only fields to change (dict). |
| `npg_get_log_stats` | Get log statistics. |
| `npg_list_audit_logs` | List audit log entries. |
| `npg_list_system_logs` | List system logs. |
| `npg_list_log_files` | List all log files. |
| `npg_download_log_file` | Download a log file by its filename. |
| `npg_view_log_file` | View the contents of a log file. |
| `npg_rotate_log_file` | Rotate a log file by its filename. |
| `npg_delete_log_file` | Delete a log file by its filename. |
| `npg_post_log` | Insert a log entry manually. REQUIRED: level, message. Optional: source, component, tags. |
| `npg_cleanup_logs` | Delete nginx access logs older than the configured retention period. |
| `npg_get_log_autocomplete_hosts` | Get distinct hosts seen in nginx access logs (for autocomplete). |
| `npg_get_log_autocomplete_ips` | Get distinct client IPs seen in nginx access logs (for autocomplete). |
| `npg_get_log_autocomplete_user_agents` | Get distinct User-Agents seen in nginx access logs (for autocomplete). |
| `npg_get_log_autocomplete_uris` | Get distinct request URIs seen in nginx access logs (for autocomplete). |
| `npg_get_log_autocomplete_countries` | Get distinct countries seen in nginx access logs (for autocomplete). |
| `npg_get_log_autocomplete_methods` | Get distinct HTTP methods seen in nginx access logs (for autocomplete). |
| `npg_get_log_filter_presets` | List saved log filter presets. |
| `npg_create_log_filter_preset` | Save a log filter preset. REQUIRED: name, filter (dict). Optional: description. |
| `npg_update_log_filter_preset` | Update a log filter preset (rename and/or replace filter). REQUIRED: preset_id. Optional: name, filter, description. |
| `npg_delete_log_filter_preset` | Delete a log filter preset by its ID. |
| `npg_cleanup_system_logs` | Delete old system logs beyond the configured retention period. |
| `npg_get_system_log_sources` | Get selectable system log sources (docker_api, docker_nginx, health_check, etc.). |
| `npg_get_system_log_levels` | Get selectable system log levels (debug, info, warn, error, fatal). |
| `npg_get_system_log_stats` | Get system log statistics (counts by source/level). |
| `npg_get_system_settings_logs` | Get the container log collector configuration. |
| `npg_update_system_settings_logs` | Update the container log collector configuration (partial update). Pass only fields to change. |
| `npg_get_audit_log_actions` | List the action values present in the audit log (for filtering). |
| `npg_get_audit_log_resource_types` | List the resource types present in the audit log (for filtering). |
| `npg_get_audit_log_api_tokens` | List recent API token usage across all tokens. |

### Security & WAF (27)

| Tool | Description |
|------|-------------|
| `npg_list_exploit_rules` | List exploit block rules. |
| `npg_get_exploit_rule` | Get an exploit rule by its ID. |
| `npg_create_exploit_rule` | Create an exploit block rule. Required: category, name, pattern, pattern_type (e.g. 'query_string'). Optional: severity, description. |
| `npg_update_exploit_rule` | Update an exploit rule. Pass only fields to change (dict). |
| `npg_delete_exploit_rule` | Delete an exploit rule by its ID. |
| `npg_toggle_exploit_rule` | Toggle an exploit rule's enabled status. |
| `npg_list_waf_rules` | List all WAF (Web Application Firewall) rules. |
| `npg_get_waf_hosts` | Get WAF config for all proxy hosts. |
| `npg_get_waf_host_config` | Get WAF config for a specific proxy host. |
| `npg_disable_waf_rule` | Disable a WAF rule for a specific proxy host. |
| `npg_get_global_security_headers` | GET global security headers configuration. |
| `npg_update_global_security_headers` | UPDATE global security headers configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options, x_content_type_options, x_xss_protection, referrer_policy, content_security_policy. |
| `npg_get_global_bot_filter` | GET global bot filter configuration. |
| `npg_update_global_bot_filter` | UPDATE global bot filter configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, block_bad_bots, block_ai_bots, allow_search_engines, block_suspicious_clients, challenge_suspicious, custom_blocked_agents, custom_allowed_agents. |
| `npg_get_global_rate_limit` | GET global rate limit configuration. |
| `npg_update_global_rate_limit` | UPDATE global rate limit configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, requests_per_second, burst_size, zone_size, limit_by, limit_response. |
| `npg_get_global_waf` | GET global WAF configuration. |
| `npg_update_global_waf` | UPDATE global WAF configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, paranoia_level, anomaly_threshold, rules (list of {id, enabled}). |
| `npg_get_exploit_rules_hosts` | List proxy hosts that have exploit blocking enabled. |
| `npg_get_exploit_rules_for_host` | List exploit rules with this host's exclusion status. REQUIRED: host_id. |
| `npg_exclude_exploit_rule_from_host` | Exclude an exploit rule on ONE proxy host (stop it blocking there). REQUIRED: host_id, rule_id. |
| `npg_remove_exploit_rule_exclusion_from_host` | Remove a host exclusion for an exploit rule (re-enable the rule for that host). REQUIRED: host_id, rule_id. |
| `npg_global_exclude_exploit_rule` | Exclude an exploit rule on EVERY host (stop it blocking anywhere). REQUIRED: rule_id. |
| `npg_remove_exploit_rule_global_exclusion` | Remove a global exclusion for an exploit rule (re-enable the rule everywhere). REQUIRED: rule_id. |
| `npg_get_waf_test_patterns` | List the built-in WAF attack test patterns. |
| `npg_test_waf_pattern` | Fire one attack payload at a target URL for WAF testing. REQUIRED: target_url, pattern (pattern name or index). |
| `npg_test_waf_all_patterns` | Fire every attack payload at a target URL for comprehensive WAF testing. REQUIRED: target_url. |

### DNS Providers (15)

| Tool | Description |
|------|-------------|
| `npg_list_dns_providers` | List all DNS providers configured for DNS-01 challenges. |
| `npg_get_dns_provider` | Get a DNS provider by its ID. |
| `npg_create_dns_provider` | Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}). |
| `npg_update_dns_provider` | Update a DNS provider. Pass only fields to change (dict). |
| `npg_delete_dns_provider` | Delete a DNS provider by its ID. |
| `npg_test_dns_provider` | Test DNS provider credentials. |
| `npg_list_ddns_records` | List all DDNS records. |
| `npg_create_ddns_record` | Create a DDNS record. REQUIRED: proxy_host_id, domain, provider_id. Optional: proxied (bool). |
| `npg_get_ddns_record` | Get a DDNS record by its ID. |
| `npg_update_ddns_record` | Update a DDNS record (partial update). Pass only fields to change. |
| `npg_delete_ddns_record` | Delete a DDNS record by its ID. |
| `npg_sync_ddns_records` | Sync all enabled DDNS records now (force immediate DNS update for all records). |
| `npg_sync_ddns_record` | Sync one DDNS record now (force DNS update for a specific record). REQUIRED: record_id. |
| `npg_import_ddns_from_hosts` | Import DDNS records from existing proxy hosts that have DDNS enabled. |
| `npg_get_dns_provider_default` | Get the default DNS provider for certificate issuance. |

### Authentication (18)

| Tool | Description |
|------|-------------|
| `npg_get_auth_status` | GET authentication status — returns whether the current session is authenticated and basic user info. |
| `npg_get_auth_account` | GET own account info — returns the authenticated user's account details. |
| `npg_auth_change_credentials` | Change own username and password (initial setup). REQUIRED: current_password, new_username, new_password. Used to complete forced initial setup. |
| `npg_auth_change_username` | Change own username. REQUIRED: current_password, new_username. |
| `npg_auth_2fa_setup` | Begin 2FA enrolment — returns QR code / secret for the user to scan with their authenticator app. |
| `npg_auth_2fa_enable` | Enable 2FA. REQUIRED: password, totp_code (6-digit code from authenticator). |
| `npg_auth_2fa_disable` | Disable 2FA. REQUIRED: password, totp_code. |
| `npg_get_auth_language` | GET the authenticated user's UI language preference. |
| `npg_update_auth_language` | SET the authenticated user's UI language. REQUIRED: language (e.g. 'en', 'ko'). |
| `npg_get_auth_font` | GET the authenticated user's UI font family preference. |
| `npg_update_auth_font` | SET the authenticated user's UI font family. REQUIRED: font (e.g. 'Inter', 'Roboto'). |
| `npg_get_auth_sso_providers` | List SSO providers available for the login screen (public-facing). |
| `npg_auth_sso_start` | Begin an SSO login flow. REQUIRED: slug (the SSO provider identifier). Returns a redirect URL. |
| `npg_list_auth_providers` | List ForwardAuth (Authelia, Authentik, custom) providers. |
| `npg_create_auth_provider` | Create a ForwardAuth provider. REQUIRED: name, type, config dict (provider-specific). |
| `npg_get_auth_provider` | Get a ForwardAuth provider by its ID. |
| `npg_update_auth_provider` | Update a ForwardAuth provider (partial update). Pass only fields to change. |
| `npg_delete_auth_provider` | Delete a ForwardAuth provider by its ID. |

### Certificates (15)

| Tool | Description |
|------|-------------|
| `npg_list_certificates` | List all SSL/TLS certificates. |
| `npg_get_certificate` | Get a certificate by its ID. |
| `npg_create_certificate` | Request a new Let's Encrypt certificate. Required: domain_names (array), email. Optional: provider (e.g. 'letsencrypt'), dns_provider_id, etc. |
| `npg_delete_certificate` | Delete a certificate by its ID. |
| `npg_renew_certificate` | Renew a certificate by its ID. |
| `npg_get_expiring_certificates` | Get certificates that are expiring soon. |
| `npg_get_certificate_history` | Get certificate history. |
| `npg_upload_certificate` | Upload a certificate file. Required: domain_names, cert_content, key_content. |
| `npg_import_from_hosts` | Import certificates from existing hosts. |
| `npg_test_acme` | Test ACME configuration for DNS provider. |
| `npg_delete_certificate_errors` | Bulk-delete all certificates in error status. |
| `npg_clear_certificate_error` | Clear a certificate's error state (mark as resolved). REQUIRED: cert_id. |
| `npg_upload_certificate_pem` | Replace the PEM material of a custom certificate. REQUIRED: cert_id, pem_content (full PEM string). |
| `npg_get_certificate_logs` | Get the issuance log stream for a certificate. REQUIRED: cert_id. |
| `npg_get_certificate_download` | Download certificate material (PEM). REQUIRED: cert_id. |

### Filter Subscriptions (15)

| Tool | Description |
|------|-------------|
| `npg_get_catalog` | Get the curated filter subscription catalog. Returns metadata (name, description, type, path, entry count) from the public npg-filters index — no entries or database rows. |
| `npg_list_filter_subscriptions` | List all filter subscriptions (remote IP/UA blocklists). |
| `npg_get_filter_subscription_catalog` | Get the curated filter catalog — list of available filter lists to subscribe to. |
| `npg_subscribe_filter_catalog` | Subscribe to one or more catalog filter lists. REQUIRED: paths (list of catalog list paths, e.g. 'lists/ips/web-scanners.json'). |
| `npg_create_filter_subscription` | Subscribe to a filter list URL. REQUIRED: url. Optional: name. |
| `npg_get_filter_subscription` | Get a filter subscription with its entries and exclusions. REQUIRED: subscription_id. |
| `npg_update_filter_subscription` | Update a filter subscription (partial update). Pass only fields to change. |
| `npg_delete_filter_subscription` | Delete a filter subscription by its ID. |
| `npg_refresh_filter_subscription` | Re-fetch entries for a filter subscription now. REQUIRED: subscription_id. |
| `npg_get_filter_subscription_exclusions` | List host exclusions of a filter subscription (hosts that skip this subscription). REQUIRED: subscription_id. |
| `npg_add_filter_subscription_exclusion` | Exclude a proxy host from a filter subscription. REQUIRED: subscription_id, host_id. |
| `npg_remove_filter_subscription_exclusion` | Remove a host exclusion from a filter subscription. REQUIRED: subscription_id, host_id. |
| `npg_get_filter_subscription_entry_exclusions` | List entry exclusions of a filter subscription (specific entries that are skipped). REQUIRED: subscription_id. |
| `npg_add_filter_subscription_entry_exclusion` | Exclude a single entry value from a filter subscription. REQUIRED: subscription_id, entry_value. |
| `npg_remove_filter_subscription_entry_exclusion` | Remove an entry exclusion from a filter subscription. REQUIRED: subscription_id, entry_value. |

### Cloud Providers (13)

| Tool | Description |
|------|-------------|
| `npg_list_cloud_providers` | List all cloud providers (for certificate DNS challenges). |
| `npg_get_cloud_provider` | Get a cloud provider by its slug. |
| `npg_create_cloud_provider` | Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description. |
| `npg_update_cloud_provider` | Update a cloud provider by its slug. Pass only fields to change (dict). |
| `npg_delete_cloud_provider` | Delete a cloud provider by its slug. |
| `npg_get_proxy_host_cloud_blocking` | GET per-host cloud provider blocking configuration. Returns blocked_providers, challenge_mode, allow_search_bots, cloud_disable_global. |
| `npg_update_proxy_host_cloud_blocking` | UPDATE per-host cloud provider blocking (the endpoint full-replaces all fields, so the tool reads current settings and merges — omitted fields are left as-is). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool), cloud_disable_global (bool \| None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global). |
| `npg_list_cloud_providers_by_region` | List cloud providers filtered by region. |
| `npg_get_cloudflare_tunnel` | Get Cloudflare Tunnel configuration. |
| `npg_update_cloudflare_tunnel` | Update Cloudflare Tunnel configuration. Pass only fields to change. |
| `npg_get_cloudflare_tunnel_status` | Get Cloudflare Tunnel status. |
| `npg_get_global_cloud_providers` | GET global cloud providers configuration. |
| `npg_update_global_cloud_providers` | UPDATE global cloud providers configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool). |

### URI Block (10)

| Tool | Description |
|------|-------------|
| `npg_list_uri_blocks` | List all URI blocks (global and per-host). |
| `npg_create_uri_block` | Create a URI block for a proxy host. Required: host_id, pattern, action (block/allow). Optional: is_regex. |
| `npg_get_uri_block` | Get a URI block by its ID. |
| `npg_update_uri_block` | Update a URI block. Pass only fields to change. |
| `npg_delete_uri_block` | Delete a URI block by its ID. |
| `npg_bulk_add_uri_block_rule` | Bulk add URI block rules. Required: rules (list of {pattern, action, is_regex}). |
| `npg_get_global_uri_block` | GET global URI block configuration. |
| `npg_update_global_uri_block` | UPDATE global URI block configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips. |
| `npg_add_global_uri_block_rule` | Add a rule to the global URI block. Required: pattern, action. Optional: is_regex. |
| `npg_delete_global_uri_block_rule` | Delete a rule from the global URI block by its ID. |

### Settings (11)

| Tool | Description |
|------|-------------|
| `npg_get_settings` | Get global NPG settings. |
| `npg_update_settings` | Update global NPG settings. Pass only fields to change (dict). |
| `npg_get_system_settings` | Get system settings (server name, timezone, locale). |
| `npg_update_system_settings` | Update system settings. Pass only fields to change (dict). |
| `npg_get_dashboard` | Get dashboard data (summary of proxy hosts, certificates, etc.). |
| `npg_get_dashboard_health` | Get system health status. |
| `npg_get_dashboard_geoip_stats` | GET GeoIP statistics by country for the dashboard. |
| `npg_get_public_ui_settings` | Get public UI settings (accessible without auth). |
| `npg_reset_settings` | Reset global nginx settings to defaults. DESTRUCTIVE — this clears all custom settings. |
| `npg_get_settings_presets` | List available global settings presets that can be applied. |
| `npg_apply_settings_preset` | Apply a global settings preset. REQUIRED: preset (preset name/identifier). |

### Backups (8)

| Tool | Description |
|------|-------------|
| `npg_list_backups` | List all backups. |
| `npg_get_backup` | Get a backup by its ID. |
| `npg_create_backup` | Create a new backup. |
| `npg_delete_backup` | Delete a backup by its ID. |
| `npg_restore_backup` | Restore from a backup. Required: backup_id. |
| `npg_download_backup` | Download a backup by its ID. |
| `npg_upload_restore_backup` | Upload and restore from a backup file. |
| `npg_get_backup_stats` | Get backup statistics. |

### API Tokens (8)

| Tool | Description |
|------|-------------|
| `npg_list_api_tokens` | List all API tokens. |
| `npg_get_api_token` | Get an API token by its ID. |
| `npg_create_api_token` | Create a new API token. Required: name, permissions (array). Optional: expires_at. |
| `npg_update_api_token` | Update an API token. Pass only fields to change (dict). |
| `npg_revoke_api_token` | Revoke an API token by its ID. |
| `npg_delete_api_token` | Delete an API token by its ID. |
| `npg_get_api_token_permissions` | List the permission strings an API token may carry (reference list). |
| `npg_get_api_token_usage` | Get recent usage for an API token. REQUIRED: token_id. |

### Users (9)

| Tool | Description |
|------|-------------|
| `npg_list_users` | List all users. |
| `npg_get_user` | Get a user by their ID. |
| `npg_create_user` | Create a new user. Required: username, email, password. Optional: role_id, is_active. |
| `npg_set_user_password` | Set/reset a user's password. Required: user_id, new_password. |
| `npg_assign_user_role` | Assign a role to a user. Required: user_id, role_id. |
| `npg_end_user_sessions` | End all sessions for a user (force logout). Required: user_id. |
| `npg_delete_user` | Delete a user by their ID. |
| `npg_get_permission_areas` | Get the permission area/verb matrix — all available permission scopes. |
| `npg_set_user_role` | Assign a role to a user account. REQUIRED: user_id, role_id. |

### SSO Providers (7)

| Tool | Description |
|------|-------------|
| `npg_list_sso_providers` | List all SSO providers. |
| `npg_create_sso_provider` | Create a new SSO provider. Required: slug, name, issuer_url, client_id. Optional: client_secret (defaults to placeholder), scopes. |
| `npg_update_sso_provider` | Update an SSO provider. Pass only fields to change. Required: provider_id. Optional: name, slug, issuer_url, client_id, client_secret (send '********' to leave unchanged), scopes. |
| `npg_delete_sso_provider` | Delete an SSO provider by its ID. |
| `npg_test_sso_provider` | Test SSO provider configuration by initiating a test login flow. |
| `npg_add_proxy_host_uri_block_rule` | Add a single URI block rule to a proxy host. REQUIRED: host_id, pattern (str or regex), action (block/allow). Optional: case_sensitive (bool). |
| `npg_delete_proxy_host_uri_block_rule` | Remove a single URI block rule from a proxy host. REQUIRED: host_id, rule_id. |

### Dashboard (3)

| Tool | Description |
|------|-------------|
| `npg_get_dashboard_containers` | Get Docker container statistics for the dashboard. |
| `npg_get_dashboard_stats` | Get hourly statistics for the dashboard. |
| `npg_get_dashboard_health_history` | Get system health history for the dashboard. |

### IP Management (4)

| Tool | Description |
|------|-------------|
| `npg_bulk_unban_ips` | Unban multiple banned-IP records at once. REQUIRED: ids (list of record IDs). |
| `npg_get_ban_history` | Get ban/unban event history. |
| `npg_get_ban_history_stats` | Get ban/unban history statistics. |
| `npg_get_ban_history_for_ip` | Get ban history for a specific IP address. REQUIRED: ip. |

### Notification Channels (8)

| Tool | Description |
|------|-------------|
| `npg_list_notification_channels` | List all notification channels. |
| `npg_create_notification_channel` | Create a notification channel. Required: name, type (e.g. 'email', 'telegram', 'slack'). Optional: config (dict). |
| `npg_update_notification_channel` | Update a notification channel. Pass only fields to change. |
| `npg_delete_notification_channel` | Delete a notification channel by its ID. |
| `npg_test_notification_channel` | Test a notification channel by sending a test message. |
| `npg_get_notification_deliveries` | Get delivery history for a notification channel. |
| `npg_detect_telegram_chats` | Detect available Telegram chats for notification delivery. |
| `npg_get_notification_channel_deliveries` | List recent deliveries for a notification channel. REQUIRED: channel_id. |

### Redirect Hosts (6)

| Tool | Description |
|------|-------------|
| `npg_list_redirect_hosts` | List all redirect hosts. |
| `npg_get_redirect_host` | Get a redirect host by its ID. |
| `npg_create_redirect_host` | Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, default 301). |
| `npg_update_redirect_host` | Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code. |
| `npg_delete_redirect_host` | Delete a redirect host by its ID. |
| `npg_sync_redirect_hosts` | Regenerate every redirect host config and reload nginx. |

### Access Lists (5)

| Tool | Description |
|------|-------------|
| `npg_list_access_lists` | List all access lists (authentication/restriction lists). |
| `npg_get_access_list` | Get an access list by its ID. |
| `npg_create_access_list` | Create a new access list. Required: name, advanced_config (block/allow rules). |
| `npg_update_access_list` | Update an access list. Pass only fields to change. |
| `npg_delete_access_list` | Delete an access list by its ID. |

### Geo (10)

| Tool | Description |
|------|-------------|
| `npg_get_geoip_status` | Get GeoIP database update status. |
| `npg_update_geoip` | Update GeoIP databases. |
| `npg_list_countries` | List available country codes for GeoIP blocking. |
| `npg_get_proxy_host_geo` | GET geo restriction configuration for a proxy host. |
| `npg_create_proxy_host_geo` | CREATE geo restriction for a proxy host. Required: host_id, countries (list of ISO codes, min 1). Optional: mode (whitelist/blacklist, default blacklist), allowed_ips, challenge_mode, disable_global (bool — false=inherit, true=disable global), allow_private_ips, allow_search_bots |
| `npg_update_proxy_host_geo` | UPDATE geo restriction for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode, disable_global (bool \| None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), allow_private_ips, allow_search_bots |
| `npg_delete_proxy_host_geo` | DELETE geo restriction for a proxy host. |
| `npg_get_global_geo` | GET global GeoIP restriction configuration. |
| `npg_update_global_geo` | UPDATE global GeoIP restriction configuration (partial update — only provided fields are changed; omitted fields are left as-is. The global default is inherited by hosts without their own override). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, allow_private_ips, allow_search_bots, challenge_mode |
| `npg_get_geoip_history` | List GeoIP database update runs and their status. |

### Fail2ban & Challenge (3)

| Tool | Description |
|------|-------------|
| `npg_get_challenge_config` | GET the global CAPTCHA challenge configuration. |
| `npg_update_challenge_config` | UPDATE the global CAPTCHA challenge configuration (partial update). Pass only fields to change. |
| `npg_get_challenge_stats` | GET CAPTCHA challenge statistics. |

### Banned IPs & Bots (5)

| Tool | Description |
|------|-------------|
| `npg_list_banned_ips` | List banned IP addresses. |
| `npg_ban_ip` | Ban an IP address. Required: ip. Optional: ban_time (seconds). |
| `npg_unban_ip` | Unban an IP by its ID. |
| `npg_get_bots_known` | Get list of known bot user-agent signatures. |
| `npg_get_security_headers_presets` | Get available security header presets. |

### Roles (4)

| Tool | Description |
|------|-------------|
| `npg_list_roles` | List all roles. |
| `npg_create_role` | Create a new role. Required: name, permissions (array of permission strings). |
| `npg_update_role` | Update a role. Pass only fields to change. |
| `npg_delete_role` | Delete a role by its ID. |

### System (11)

| Tool | Description |
|------|-------------|
| `npg_check_update` | Check for available NPG updates. |
| `npg_get_health_detailed` | Get a detailed health snapshot (detailed version of health check). |
| `npg_get_status` | Get component status — health of all NPG subsystems. |
| `npg_check_npg_update` | Check for a newer NPG release version. |
| `npg_get_waf_global_rules` | List all OWASP CRS rules with their GLOBAL exclusion status. |
| `npg_get_waf_global_exclusions` | List the globally disabled CRS rules. |
| `npg_get_waf_global_history` | Get the global WAF policy change history. |
| `npg_disable_waf_global_rule` | Disable a CRS rule for EVERY host (globally). REQUIRED: rule_id. |
| `npg_enable_waf_global_rule` | Re-enable a CRS rule globally (remove global disable). REQUIRED: rule_id. |
| `npg_get_waf_host_history` | Get the WAF policy change history for a proxy host. REQUIRED: host_id. |
| `npg_disable_waf_rule_by_host` | Disable a CRS rule on the host that owns a domain name. REQUIRED: domain_name, rule_id. |

### SSL / Nginx (3)

| Tool | Description |
|------|-------------|
| `npg_reload_nginx` | Reload nginx configuration without full restart. |
| `npg_sync_nginx` | Sync all configs and reload nginx. |
| `npg_test_nginx` | Test nginx configuration for validity. |

### System & Health (1)

| Tool | Description |
|------|-------------|
| `npg_get_upstream_health` | GET health status of an upstream pool. REQUIRED: upstream_id (UUID string). |

### Docker (1)

| Tool | Description |
|------|-------------|
| `npg_get_docker_containers` | Get status of all Docker containers managed by NPG. |
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
| `MCP_ALLOWED_HOSTS` | `localhost:port` | Comma-separated `host:port` whose `Host` header the endpoint accepts |
| `MCP_ALLOWED_ORIGINS` | *(empty)* | Comma-separated origins accepted for cross-origin requests; restricts CSRF |
| `MCP_REBINDING_PROTECTION` | `true` | Enable DNS-rebinding protection (disable only if it breaks your proxy) |

## Project Structure

```
npg_mcp/
  main.py       # All 286 MCP tools
  client.py     # HTTP client wrapper with auto-auth
  __init__.py
Dockerfile      # Multi-stage Docker build
docker-compose.yml
pyproject.toml  # Dependencies: mcp>=1.0, httpx>=0.27
tool-schemas.yaml  # Full input parameter schemas for all 286 tools
```

## License

MIT

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
| **Proxy Hosts** | 38 tools |
| **Logs** | 36 tools |
| **Security & WAF** | 32 tools |
| **DNS Providers** | 15 tools |
| **Authentication** | 15 tools |
| **Certificates** | 12 tools |
| **Filter Subscriptions** | 12 tools |
| **Cloud Providers** | 11 tools |
| **URI Block** | 10 tools |
| **Settings** | 8 tools |
| **Backups** | 8 tools |
| **API Tokens** | 8 tools |
| **Users** | 8 tools |
| **SSO Providers** | 7 tools |
| **Other** | 6 tools |
| **Dashboard** | 6 tools |
| **IP Management** | 6 tools |
| **Notification Channels** | 6 tools |
| **Redirect Hosts** | 5 tools |
| **Access Lists** | 5 tools |
| **Geo** | 5 tools |
| **Fail2ban & Challenge** | 4 tools |
| **Banned IPs & Bots** | 4 tools |
| **Roles** | 4 tools |
| **System** | 4 tools |
| **SSL / Nginx** | 3 tools |
| **System & Health** | 2 tools |
| **Docker** | 1 tools |

### Proxy Hosts (38)

| Tool | Description |
|------|-------------|
| `npg_list_proxy_hosts` | List all proxy hosts |
| `npg_get_proxy_host` | Get a single proxy host by ID |
| `npg_get_proxy_host_by_domain` | Get a proxy host by domain name |
| `npg_create_proxy_host` | Create a new reverse proxy host |
| `npg_update_proxy_host` | Update an existing proxy host (partial update) |
| `npg_delete_proxy_host` | Delete a proxy host by ID |
| `npg_test_proxy_host` | Test upstream connectivity |
| `npg_sync_proxy_hosts` | Sync all proxy host configs and reload nginx |
| `npg_clone_proxy_host` | Clone a proxy host with new domain names |
| `npg_get_proxy_host_rate_limit` | GET rate limit configuration |
| `npg_update_proxy_host_rate_limit` | UPDATE rate limit configuration |
| `npg_get_proxy_host_bot_filter` | GET bot filter configuration |
| `npg_update_proxy_host_bot_filter` | UPDATE bot filter configuration |
| `npg_delete_proxy_host_bot_filter` | Delete the bot filter config (falls back to global) |
| `npg_get_proxy_host_security_headers` | GET security headers configuration |
| `npg_update_proxy_host_security_headers` | UPDATE security headers configuration |
| `npg_delete_proxy_host_security_headers` | Delete security headers config (falls back to global) |
| `npg_get_proxy_host_upstream` | GET upstream/load balancing configuration |
| `npg_update_proxy_host_upstream` | UPDATE upstream/load balancing configuration |
| `npg_delete_proxy_host_upstream` | Delete upstream config (falls back to defaults) |
| `npg_get_proxy_host_uri_block` | GET URI block configuration |
| `npg_update_proxy_host_uri_block` | UPDATE URI block configuration |
| `npg_delete_proxy_host_uri_block` | Delete URI block config (falls back to global) |
| `npg_add_proxy_host_uri_block_rule` | Add a single URI block rule |
| `npg_delete_proxy_host_uri_block_rule` | Remove a single URI block rule |
| `npg_get_proxy_host_geo` | GET geo restriction configuration |
| `npg_create_proxy_host_geo` | CREATE geo restriction |
| `npg_update_proxy_host_geo` | UPDATE geo restriction |
| `npg_delete_proxy_host_geo` | DELETE geo restriction |
| `npg_get_proxy_host_fail2ban` | GET fail2ban configuration |
| `npg_update_proxy_host_fail2ban` | UPDATE fail2ban configuration |
| `npg_delete_proxy_host_fail2ban` | Delete fail2ban config (falls back to global) |
| `npg_get_proxy_host_challenge` | GET CAPTCHA/challenge configuration |
| `npg_update_proxy_host_challenge` | UPDATE CAPTCHA/challenge configuration |
| `npg_delete_proxy_host_challenge` | DELETE CAPTCHA/challenge configuration |
| `npg_set_proxy_host_favorite` | Toggle a proxy host as a favorite |
| `npg_get_proxy_host_cloud_blocking` | GET per-host cloud provider blocking |
| `npg_update_proxy_host_cloud_blocking` | UPDATE per-host cloud provider blocking |
| `npg_regenerate_config` | Regenerate nginx config for a specific proxy host |

### Logs (36)

| Tool | Description |
|------|-------------|
| `npg_get_logs` | Get access logs |
| `npg_get_log_settings` | Get log settings |
| `npg_update_log_settings` | Update log settings |
| `npg_get_log_stats` | Get log statistics |
| `npg_list_audit_logs` | List audit log entries |
| `npg_list_system_logs` | List system logs |
| `npg_list_log_files` | List all log files |
| `npg_download_log_file` | Download a log file by filename |
| `npg_view_log_file` | View the contents of a log file |
| `npg_rotate_log_file` | Rotate a log file by filename |
| `npg_delete_log_file` | Delete a log file by filename |
| `npg_get_catalog` | Get the curated filter subscription catalog |
| `npg_get_filter_subscription_catalog` | Get the curated filter catalog |
| `npg_subscribe_filter_catalog` | Subscribe to one or more catalog filter lists |
| `npg_get_certificate_logs` | Get the issuance log stream for a certificate |
| `npg_post_log` | Insert a log entry manually |
| `npg_cleanup_logs` | Delete nginx access logs older than retention period |
| `npg_get_log_autocomplete_hosts` | Get distinct hosts seen in access logs |
| `npg_get_log_autocomplete_ips` | Get distinct client IPs seen in access logs |
| `npg_get_log_autocomplete_user_agents` | Get distinct User-Agents seen in access logs |
| `npg_get_log_autocomplete_uris` | Get distinct request URIs seen in access logs |
| `npg_get_log_autocomplete_countries` | Get distinct countries seen in access logs |
| `npg_get_log_autocomplete_methods` | Get distinct HTTP methods seen in access logs |
| `npg_get_log_filter_presets` | List saved log filter presets |
| `npg_create_log_filter_preset` | Save a log filter preset |
| `npg_update_log_filter_preset` | Update a log filter preset |
| `npg_delete_log_filter_preset` | Delete a log filter preset |
| `npg_cleanup_system_logs` | Delete old system logs beyond retention period |
| `npg_get_system_log_sources` | Get selectable system log sources |
| `npg_get_system_log_levels` | Get selectable system log levels |
| `npg_get_system_log_stats` | Get system log statistics |
| `npg_get_system_settings_logs` | Get the container log collector configuration |
| `npg_update_system_settings_logs` | Update the container log collector configuration |
| `npg_get_audit_log_actions` | List action values present in the audit log |
| `npg_get_audit_log_resource_types` | List resource types present in the audit log |
| `npg_get_audit_log_api_tokens` | List recent API token usage across all tokens |

### Security & WAF (32)

| Tool | Description |
|------|-------------|
| `npg_apply_security_header_preset` | APPLY a security header preset (strict/balanced/relaxed) |
| `npg_get_security_headers_presets` | Get available security header presets |
| `npg_list_exploit_rules` | List exploit block rules |
| `npg_get_exploit_rule` | Get an exploit rule by ID |
| `npg_create_exploit_rule` | Create an exploit block rule |
| `npg_update_exploit_rule` | Update an exploit rule |
| `npg_delete_exploit_rule` | Delete an exploit rule |
| `npg_toggle_exploit_rule` | Toggle an exploit rule's enabled status |
| `npg_list_waf_rules` | List all WAF rules |
| `npg_get_waf_hosts` | Get WAF config for all proxy hosts |
| `npg_get_waf_host_config` | Get WAF config for a specific proxy host |
| `npg_disable_waf_rule` | Disable a WAF rule for a specific proxy host |
| `npg_get_global_security_headers` | GET global security headers configuration |
| `npg_update_global_security_headers` | UPDATE global security headers configuration |
| `npg_get_global_waf` | GET global WAF configuration |
| `npg_update_global_waf` | UPDATE global WAF configuration |
| `npg_get_exploit_rules_hosts` | List proxy hosts that have exploit blocking enabled |
| `npg_get_exploit_rules_for_host` | List exploit rules with a host's exclusion status |
| `npg_exclude_exploit_rule_from_host` | Exclude an exploit rule on ONE proxy host |
| `npg_remove_exploit_rule_exclusion_from_host` | Remove a host exclusion for an exploit rule |
| `npg_global_exclude_exploit_rule` | Exclude an exploit rule on EVERY host |
| `npg_remove_exploit_rule_global_exclusion` | Remove a global exclusion for an exploit rule |
| `npg_get_waf_global_rules` | List all OWASP CRS rules with global exclusion status |
| `npg_get_waf_global_exclusions` | List the globally disabled CRS rules |
| `npg_get_waf_global_history` | Get the global WAF policy change history |
| `npg_disable_waf_global_rule` | Disable a CRS rule globally |
| `npg_enable_waf_global_rule` | Re-enable a CRS rule globally |
| `npg_get_waf_host_history` | Get the WAF policy change history for a proxy host |
| `npg_disable_waf_rule_by_host` | Disable a CRS rule on the host that owns a domain |
| `npg_get_waf_test_patterns` | List the built-in WAF attack test patterns |
| `npg_test_waf_pattern` | Fire one attack payload at a target URL |
| `npg_test_waf_all_patterns` | Fire every attack payload at a target URL |

### DNS Providers (15)

| Tool | Description |
|------|-------------|
| `npg_list_dns_providers` | List all DNS providers for DNS-01 challenges |
| `npg_get_dns_provider` | Get a DNS provider by ID |
| `npg_create_dns_provider` | Create a DNS provider for DNS-01 challenges |
| `npg_update_dns_provider` | Update a DNS provider |
| `npg_delete_dns_provider` | Delete a DNS provider |
| `npg_test_dns_provider` | Test DNS provider credentials |
| `npg_list_ddns_records` | List all DDNS records |
| `npg_create_ddns_record` | Create a DDNS record |
| `npg_get_ddns_record` | Get a DDNS record by ID |
| `npg_update_ddns_record` | Update a DDNS record |
| `npg_delete_ddns_record` | Delete a DDNS record |
| `npg_sync_ddns_records` | Sync all enabled DDNS records now |
| `npg_sync_ddns_record` | Sync one DDNS record now |
| `npg_import_ddns_from_hosts` | Import DDNS records from existing proxy hosts |
| `npg_get_dns_provider_default` | Get the default DNS provider for certificate issuance |

### Authentication (15)

| Tool | Description |
|------|-------------|
| `npg_get_auth_status` | GET authentication status |
| `npg_get_auth_account` | GET own account info |
| `npg_auth_change_credentials` | Change own username and password (initial setup) |
| `npg_auth_2fa_setup` | Begin 2FA enrolment (returns QR code) |
| `npg_auth_2fa_enable` | Enable 2FA |
| `npg_auth_2fa_disable` | Disable 2FA |
| `npg_get_auth_language` | GET the authenticated user's UI language preference |
| `npg_update_auth_language` | SET the authenticated user's UI language |
| `npg_get_auth_font` | GET the authenticated user's UI font family preference |
| `npg_update_auth_font` | SET the authenticated user's UI font family |
| `npg_list_auth_providers` | List ForwardAuth providers (Authelia, Authentik, custom) |
| `npg_create_auth_provider` | Create a ForwardAuth provider |
| `npg_get_auth_provider` | Get a ForwardAuth provider by ID |
| `npg_update_auth_provider` | Update a ForwardAuth provider |
| `npg_delete_auth_provider` | Delete a ForwardAuth provider |

### Certificates (12)

| Tool | Description |
|------|-------------|
| `npg_list_certificates` | List all SSL/TLS certificates |
| `npg_get_certificate` | Get a certificate by ID |
| `npg_create_certificate` | Request a new Let's Encrypt certificate |
| `npg_delete_certificate` | Delete a certificate by ID |
| `npg_renew_certificate` | Renew a certificate by ID |
| `npg_get_expiring_certificates` | Get certificates that are expiring soon |
| `npg_get_certificate_history` | Get certificate history |
| `npg_upload_certificate` | Upload a certificate file |
| `npg_delete_certificate_errors` | Bulk-delete all certificates in error status |
| `npg_clear_certificate_error` | Clear a certificate's error state |
| `npg_upload_certificate_pem` | Replace the PEM material of a custom certificate |
| `npg_get_certificate_download` | Download certificate material (PEM) |

### Filter Subscriptions (12)

| Tool | Description |
|------|-------------|
| `npg_list_filter_subscriptions` | List all filter subscriptions |
| `npg_create_filter_subscription` | Subscribe to a filter list URL |
| `npg_get_filter_subscription` | Get a filter subscription with entries and exclusions |
| `npg_update_filter_subscription` | Update a filter subscription |
| `npg_delete_filter_subscription` | Delete a filter subscription |
| `npg_refresh_filter_subscription` | Re-fetch entries for a filter subscription |
| `npg_get_filter_subscription_exclusions` | List host exclusions of a filter subscription |
| `npg_add_filter_subscription_exclusion` | Exclude a proxy host from a filter subscription |
| `npg_remove_filter_subscription_exclusion` | Remove a host exclusion from a filter subscription |
| `npg_get_filter_subscription_entry_exclusions` | List entry exclusions of a filter subscription |
| `npg_add_filter_subscription_entry_exclusion` | Exclude a single entry value from a filter subscription |
| `npg_remove_filter_subscription_entry_exclusion` | Remove an entry exclusion from a filter subscription |

### Cloud Providers (11)

| Tool | Description |
|------|-------------|
| `npg_list_cloud_providers` | List all cloud providers (certificate DNS challenges) |
| `npg_get_cloud_provider` | Get a cloud provider by slug |
| `npg_create_cloud_provider` | Create a cloud provider (IP-range database entry) |
| `npg_update_cloud_provider` | Update a cloud provider by slug |
| `npg_delete_cloud_provider` | Delete a cloud provider by slug |
| `npg_list_cloud_providers_by_region` | List cloud providers filtered by region |
| `npg_get_cloudflare_tunnel` | Get Cloudflare Tunnel configuration |
| `npg_update_cloudflare_tunnel` | Update Cloudflare Tunnel configuration |
| `npg_get_cloudflare_tunnel_status` | Get Cloudflare Tunnel status |
| `npg_get_global_cloud_providers` | GET global cloud providers configuration |
| `npg_update_global_cloud_providers` | UPDATE global cloud providers configuration |

### URI Block (10)

| Tool | Description |
|------|-------------|
| `npg_list_uri_blocks` | List all URI blocks (global and per-host) |
| `npg_create_uri_block` | Create a URI block for a proxy host |
| `npg_get_uri_block` | Get a URI block by ID |
| `npg_update_uri_block` | Update a URI block |
| `npg_delete_uri_block` | Delete a URI block by ID |
| `npg_bulk_add_uri_block_rule` | Bulk add URI block rules |
| `npg_get_global_uri_block` | GET global URI block configuration |
| `npg_update_global_uri_block` | UPDATE global URI block configuration |
| `npg_add_global_uri_block_rule` | Add a rule to the global URI block |
| `npg_delete_global_uri_block_rule` | Delete a rule from the global URI block |

### Settings (8)

| Tool | Description |
|------|-------------|
| `npg_get_settings` | Get global NPG settings |
| `npg_update_settings` | Update global NPG settings |
| `npg_get_system_settings` | Get system settings (server name, timezone, locale) |
| `npg_update_system_settings` | Update system settings |
| `npg_get_public_ui_settings` | Get public UI settings (no auth required) |
| `npg_reset_settings` | Reset global nginx settings to defaults |
| `npg_get_settings_presets` | List available global settings presets |
| `npg_apply_settings_preset` | Apply a global settings preset |

### Backups (8)

| Tool | Description |
|------|-------------|
| `npg_list_backups` | List all backups |
| `npg_get_backup` | Get a backup by ID |
| `npg_create_backup` | Create a new backup |
| `npg_delete_backup` | Delete a backup by ID |
| `npg_restore_backup` | Restore from a backup |
| `npg_download_backup` | Download a backup by ID |
| `npg_upload_restore_backup` | Upload and restore from a backup file |
| `npg_get_backup_stats` | Get backup statistics |

### API Tokens (8)

| Tool | Description |
|------|-------------|
| `npg_list_api_tokens` | List all API tokens |
| `npg_get_api_token` | Get an API token by ID |
| `npg_create_api_token` | Create a new API token |
| `npg_update_api_token` | Update an API token |
| `npg_revoke_api_token` | Revoke an API token by ID |
| `npg_delete_api_token` | Delete an API token by ID |
| `npg_get_api_token_permissions` | List the permission strings an API token may carry |
| `npg_get_api_token_usage` | Get recent usage for an API token |

### Users (8)

| Tool | Description |
|------|-------------|
| `npg_list_users` | List all users |
| `npg_get_user` | Get a user by ID |
| `npg_create_user` | Create a new user |
| `npg_set_user_password` | Set/reset a user's password |
| `npg_assign_user_role` | Assign a role to a user |
| `npg_end_user_sessions` | End all sessions for a user (force logout) |
| `npg_delete_user` | Delete a user by ID |
| `npg_auth_change_username` | Change own username |

### SSO Providers (7)

| Tool | Description |
|------|-------------|
| `npg_list_sso_providers` | List all SSO providers |
| `npg_create_sso_provider` | Create a new SSO provider |
| `npg_update_sso_provider` | Update an SSO provider |
| `npg_delete_sso_provider` | Delete an SSO provider |
| `npg_test_sso_provider` | Test SSO provider configuration (test login flow) |
| `npg_get_auth_sso_providers` | List SSO providers available for the login screen |
| `npg_auth_sso_start` | Begin an SSO login flow |

### Other (6)

| Tool | Description |
|------|-------------|
| `npg_list_countries` | List available country codes for GeoIP blocking |
| `npg_detect_telegram_chats` | Detect available Telegram chats for notifications |
| `npg_import_from_hosts` | Import certificates from existing hosts |
| `npg_test_acme` | Test ACME configuration for DNS provider |
| `npg_get_global_rate_limit` | GET global rate limit configuration |
| `npg_update_global_rate_limit` | UPDATE global rate limit configuration |

### Dashboard (6)

| Tool | Description |
|------|-------------|
| `npg_get_dashboard` | Get dashboard data (summary of proxy hosts, certificates, etc.) |
| `npg_get_dashboard_health` | Get system health status |
| `npg_get_dashboard_geoip_stats` | GET GeoIP statistics by country |
| `npg_get_dashboard_containers` | Get Docker container statistics |
| `npg_get_dashboard_stats` | Get hourly statistics |
| `npg_get_dashboard_health_history` | Get system health history |

### IP Management (6)

| Tool | Description |
|------|-------------|
| `npg_ban_ip` | Ban an IP address |
| `npg_unban_ip` | Unban an IP by ID |
| `npg_bulk_unban_ips` | Unban multiple banned-IP records at once |
| `npg_get_ban_history` | Get ban/unban event history |
| `npg_get_ban_history_stats` | Get ban/unban history statistics |
| `npg_get_ban_history_for_ip` | Get ban history for a specific IP |

### Notification Channels (6)

| Tool | Description |
|------|-------------|
| `npg_list_notification_channels` | List all notification channels |
| `npg_create_notification_channel` | Create a notification channel |
| `npg_update_notification_channel` | Update a notification channel |
| `npg_delete_notification_channel` | Delete a notification channel |
| `npg_test_notification_channel` | Test a notification channel (send test message) |
| `npg_get_notification_deliveries` | Get delivery history for a notification channel |

### Redirect Hosts (5)

| Tool | Description |
|------|-------------|
| `npg_list_redirect_hosts` | List all redirect hosts |
| `npg_get_redirect_host` | Get a redirect host by ID |
| `npg_create_redirect_host` | Create a new redirect host |
| `npg_update_redirect_host` | Update a redirect host |
| `npg_delete_redirect_host` | Delete a redirect host by ID |

### Access Lists (5)

| Tool | Description |
|------|-------------|
| `npg_list_access_lists` | List all access lists (authentication/restriction lists) |
| `npg_get_access_list` | Get an access list by ID |
| `npg_create_access_list` | Create a new access list |
| `npg_update_access_list` | Update an access list |
| `npg_delete_access_list` | Delete an access list by ID |

### Geo (5)

| Tool | Description |
|------|-------------|
| `npg_get_geoip_status` | Get GeoIP database update status |
| `npg_update_geoip` | Update GeoIP databases |
| `npg_get_global_geo` | GET global GeoIP restriction configuration |
| `npg_update_global_geo` | UPDATE global GeoIP restriction configuration |
| `npg_get_geoip_history` | List GeoIP database update runs and their status |

### Fail2ban & Challenge (4)

| Tool | Description |
|------|-------------|
| `npg_verify_challenge` | Verify a CAPTCHA solution (public endpoint) |
| `npg_get_challenge_config` | GET the global CAPTCHA challenge configuration |
| `npg_update_challenge_config` | UPDATE the global CAPTCHA challenge configuration |
| `npg_get_challenge_stats` | GET CAPTCHA challenge statistics |

### Banned IPs & Bots (4)

| Tool | Description |
|------|-------------|
| `npg_list_banned_ips` | List banned IP addresses |
| `npg_get_bots_known` | Get list of known bot user-agent signatures |
| `npg_get_global_bot_filter` | GET global bot filter configuration |
| `npg_update_global_bot_filter` | UPDATE global bot filter configuration |

### Roles (4)

| Tool | Description |
|------|-------------|
| `npg_list_roles` | List all roles |
| `npg_create_role` | Create a new role |
| `npg_update_role` | Update a role |
| `npg_delete_role` | Delete a role by ID |

### System (4)

| Tool | Description |
|------|-------------|
| `npg_check_update` | Check for available NPG updates |
| `npg_get_status` | Get component status — health of all NPG subsystems |
| `npg_check_npg_update` | Check for a newer NPG release version |
| `npg_get_global_rate_limit` | GET global rate limit configuration |

### SSL / Nginx (3)

| Tool | Description |
|------|-------------|
| `npg_reload_nginx` | Reload nginx configuration without full restart |
| `npg_sync_nginx` | Sync all configs and reload nginx |
| `npg_test_nginx` | Test nginx configuration for validity |

### System & Health (2)

| Tool | Description |
|------|-------------|
| `npg_get_upstream_health` | GET health status of an upstream pool |
| `npg_get_health_detailed` | Get a detailed health snapshot |

### Docker (1)

| Tool | Description |
|------|-------------|
| `npg_get_docker_containers` | Get Docker container statistics |

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
  main.py       # All 287 MCP tools
  client.py     # HTTP client wrapper with auto-auth
  __init__.py
Dockerfile      # Multi-stage Docker build
docker-compose.yml
pyproject.toml  # Dependencies: mcp>=1.0, httpx>=0.27
tool-schemas.yaml  # Full input parameter schemas for all 287 tools
```

## License

MIT

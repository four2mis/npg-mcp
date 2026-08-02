# NPG MCP Server

**English** | [한국어](README.ko.md)

MCP server for [NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard) (NPG) — manage proxy hosts, certificates, SSL, security rules, and nginx configuration through MCP tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org/).

> **⚠️ Vibe-coded with an AI agent.** This codebase was generated at speed by an AI agent, not hand-crafted by a human. Expect rough edges, unhandled edge cases, and bugs. Do **not** deploy it to an active/production NginxProxyGuard instance without first testing against a **sandboxed / disposable NPG environment** and reviewing the code. It can create, update, delete, and reconfigure live proxy hosts, so verify in isolation before pointing it at real infrastructure.

## Features

108+ MCP tools across all NPG API categories:

| Category | Tools |
|----------|-------|
| **Auth** | login, logout, me |
| **Dashboard** | overview, health, geoip stats |
| **Proxy Hosts** | list, get, create, update, delete, test, clone, sync, regenerate |
| **Security (per-host)** | rate limit, bot filter, security headers (+presets), upstream, URI block, fail2ban, challenge/CAPTCHA |
| **Geo Restriction** | get, create, update, delete (per-host) |
| **Certificates** | list, get, create, delete, renew |
| **Redirect Hosts** | list, get, create, update, delete |
| **Access Lists** | list, get, create, update, delete |
| **DNS Providers** | list, get, create, update, delete, test |
| **Cloud Providers** | list, get, create, update, delete |
| **WAF** | list rules, get hosts/config, disable rules |
| **Exploit Rules** | list, get, create, update, delete, toggle |
| **Settings** | global settings, system settings, nginx sync |
| **Logs** | access logs, audit logs, system logs, stats |
| **Backups** | list, get, create, delete, restore |
| **API Tokens** | list, get, create, update, revoke, delete |

## Tools Reference

The server exposes **108 MCP tools** across the following categories:

- **Auth** (4)
- **Dashboard** (3)
- **Proxy Hosts** (10)
- **SSL / Nginx** (8)
- **Redirect Hosts** (5)
- **Security (per-host)** (12)
- **Geo Restriction** (5)
- **Fail2ban & Challenge** (6)
- **Access Lists** (5)
- **DNS Providers** (6)
- **Cloud Providers** (5)
- **GeoIP** (2)
- **Banned IPs & Bots** (4)
- **URI Block** (2)
- **WAF & Exploit Rules** (10)
- **Settings** (4)
- **Logs** (6)
- **Backups** (5)
- **API Tokens** (6)

### Auth (4)

| Tool | Description |
|------|-------------|
| `npg_auth_login` | Authenticate with NPG credentials. The resulting session token is stored server-side; it is not returned to the client. |
| `npg_auth_logout` | Invalidate the current session token. |
| `npg_auth_me` | Get the current authenticated user's info. |
| `npg_change_password` | Change the current user's password. REQUIRED: current_password, new_password (min 8 chars). |

### Dashboard (3)

| Tool | Description |
|------|-------------|
| `npg_get_dashboard` | Get dashboard data (summary of proxy hosts, certificates, etc.). |
| `npg_get_dashboard_health` | Get system health status. |
| `npg_get_dashboard_geoip_stats` | GET GeoIP statistics by country for the dashboard. |

### Proxy Hosts (10)

| Tool | Description |
|------|-------------|
| `npg_list_proxy_hosts` | List all proxy hosts. Returns a list of proxy host objects. |
| `npg_get_proxy_host` | Get a single proxy host by its ID. |
| `npg_get_proxy_host_by_domain` | Get a proxy host by its domain name. |
| `npg_create_proxy_host` | Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: forward_scheme, block_normal, waf_enabled, block_http, ssl_forced, ssl_cert_id, cache_enabled, etc. |
| `npg_update_proxy_host` | Update an existing proxy host. Pass only the fields you want to change. Use `?skip_nginx=true` to skip nginx regeneration. |
| `npg_delete_proxy_host` | Delete a proxy host by its ID. |
| `npg_test_proxy_host` | Test upstream connectivity for a proxy host. |
| `npg_regenerate_config` | Regenerate nginx config for a specific proxy host without touching others. |
| `npg_sync_proxy_hosts` | Sync all proxy host configs and reload nginx. |
| `npg_clone_proxy_host` | Clone a proxy host with new domain names. Returns the new proxy host. |

### SSL / Nginx (8)

| Tool | Description |
|------|-------------|
| `npg_list_certificates` | List all SSL/TLS certificates. |
| `npg_get_certificate` | Get a certificate by its ID. |
| `npg_create_certificate` | Request a new Let's Encrypt certificate. Required: domain_names (array), email. Optional: provider (e.g. 'letsencrypt'), dns_provider_id, etc. |
| `npg_delete_certificate` | Delete a certificate by its ID. |
| `npg_renew_certificate` | Renew a certificate by its ID. |
| `npg_reload_nginx` | Reload nginx configuration without full restart. |
| `npg_sync_nginx` | Sync all configs and reload nginx. |
| `npg_test_nginx` | Test nginx configuration for validity. |

### Redirect Hosts (5)

| Tool | Description |
|------|-------------|
| `npg_list_redirect_hosts` | List all redirect hosts. |
| `npg_get_redirect_host` | Get a redirect host by its ID. |
| `npg_create_redirect_host` | Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, default 301). |
| `npg_update_redirect_host` | Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code. |
| `npg_delete_redirect_host` | Delete a redirect host by its ID. |

### Security (per-host) (12)

| Tool | Description |
|------|-------------|
| `npg_get_proxy_host_rate_limit` | GET rate limit configuration for a proxy host. |
| `npg_update_proxy_host_rate_limit` | UPDATE rate limit configuration for a proxy host. Body: enabled, requests_per_second, burst_size, zone_size, limit_by (ip/uri/ip_uri), limit_response |
| `npg_get_proxy_host_bot_filter` | GET bot filter configuration for a proxy host. |
| `npg_update_proxy_host_bot_filter` | UPDATE bot filter configuration for a proxy host. Required: host_id (str\|int), enabled (bool). Optional: block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool), custom_blocked_agents (str, comma-separated list). |
| `npg_get_proxy_host_security_headers` | GET security headers configuration for a proxy host. |
| `npg_update_proxy_host_security_headers` | UPDATE security headers for a proxy host. Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options (DENY/SAMEORIGIN/''), x_content_type_options, x_xss_protection, referrer_policy, content_security_policy |
| `npg_apply_security_header_preset` | APPLY a security header preset to a proxy host. preset: strict, balanced, or relaxed. |
| `npg_get_proxy_host_upstream` | GET upstream/load balancing configuration for a proxy host. |
| `npg_update_proxy_host_upstream` | UPDATE upstream/load balancing configuration. Body: name, scheme, servers (list of {address, port, weight, backup}), load_balance, health_check_enabled, health_check_path, health_check_interval |
| `npg_get_proxy_host_uri_block` | GET URI block configuration for a proxy host. |
| `npg_update_proxy_host_uri_block` | UPDATE URI block configuration. Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips |
| `npg_get_security_headers_presets` | Get available security header presets. |

### Geo Restriction (5)

| Tool | Description |
|------|-------------|
| `npg_get_proxy_host_geo` | GET geo restriction configuration for a proxy host. |
| `npg_create_proxy_host_geo` | CREATE geo restriction for a proxy host. Body: enabled, mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode |
| `npg_update_proxy_host_geo` | UPDATE geo restriction for a proxy host. Body: enabled, mode, countries, allowed_ips, challenge_mode |
| `npg_delete_proxy_host_geo` | DELETE geo restriction for a proxy host. |
| `npg_list_countries` | List available country codes for GeoIP blocking. |

### Fail2ban & Challenge (6)

| Tool | Description |
|------|-------------|
| `npg_get_proxy_host_fail2ban` | GET fail2ban configuration for a proxy host. |
| `npg_update_proxy_host_fail2ban` | UPDATE fail2ban configuration. Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge) |
| `npg_get_proxy_host_challenge` | GET CAPTCHA/challenge configuration for a proxy host. |
| `npg_update_proxy_host_challenge` | UPDATE CAPTCHA/challenge configuration. Body: enabled, challenge_type (captcha/js_challenge), difficulty, site_key, token_validity, min_score, apply_to, page_title, challenge_ips |
| `npg_delete_proxy_host_challenge` | DELETE CAPTCHA/challenge configuration for a proxy host. |
| `npg_verify_challenge` | Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution. |

### Access Lists (5)

| Tool | Description |
|------|-------------|
| `npg_list_access_lists` | List all access lists (authentication/restriction lists). |
| `npg_get_access_list` | Get an access list by its ID. |
| `npg_create_access_list` | Create a new access list. Required: name, advanced_config (block/allow rules). |
| `npg_update_access_list` | Update an access list. Pass only fields to change. |
| `npg_delete_access_list` | Delete an access list by its ID. |

### DNS Providers (6)

| Tool | Description |
|------|-------------|
| `npg_list_dns_providers` | List all DNS providers configured for DNS-01 challenges. |
| `npg_get_dns_provider` | Get a DNS provider by its ID. |
| `npg_create_dns_provider` | Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}). |
| `npg_update_dns_provider` | Update a DNS provider. Pass only fields to change (dict). |
| `npg_delete_dns_provider` | Delete a DNS provider by its ID. |
| `npg_test_dns_provider` | Test DNS provider credentials. |

### Cloud Providers (5)

| Tool | Description |
|------|-------------|
| `npg_list_cloud_providers` | List all cloud providers (for certificate DNS challenges). |
| `npg_get_cloud_provider` | Get a cloud provider by its slug. |
| `npg_create_cloud_provider` | Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description. |
| `npg_update_cloud_provider` | Update a cloud provider by its slug. Pass only fields to change (dict). |
| `npg_delete_cloud_provider` | Delete a cloud provider by its slug. |

### GeoIP (2)

| Tool | Description |
|------|-------------|
| `npg_get_geoip_status` | Get GeoIP database update status. |
| `npg_update_geoip` | Update GeoIP databases. |

### Banned IPs & Bots (4)

| Tool | Description |
|------|-------------|
| `npg_list_banned_ips` | List banned IP addresses. |
| `npg_ban_ip` | Ban an IP address. Required: ip. Optional: ban_time (seconds). |
| `npg_unban_ip` | Unban an IP by its ID. |
| `npg_get_bots_known` | Get list of known bot user-agent signatures. |

### URI Block (2)

| Tool | Description |
|------|-------------|
| `npg_get_global_uri_block` | Get global URI block settings. |
| `npg_update_global_uri_block` | Update global URI block settings. Pass only fields to change (dict). |

### WAF & Exploit Rules (10)

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

### Settings (4)

| Tool | Description |
|------|-------------|
| `npg_get_settings` | Get global NPG settings. |
| `npg_update_settings` | Update global NPG settings. Pass only fields to change (dict). |
| `npg_get_system_settings` | Get system settings (server name, timezone, locale). |
| `npg_update_system_settings` | Update system settings. Pass only fields to change (dict). |

### Logs (6)

| Tool | Description |
|------|-------------|
| `npg_get_logs` | Get access logs. |
| `npg_get_log_settings` | Get log settings. |
| `npg_update_log_settings` | Update log settings. Pass only fields to change (dict). |
| `npg_get_log_stats` | Get log statistics. |
| `npg_list_audit_logs` | List audit log entries. |
| `npg_list_system_logs` | List system logs. |

### Backups (5)

| Tool | Description |
|------|-------------|
| `npg_list_backups` | List all backups. |
| `npg_get_backup` | Get a backup by its ID. |
| `npg_create_backup` | Create a new backup. |
| `npg_delete_backup` | Delete a backup by its ID. |
| `npg_restore_backup` | Restore from a backup. Required: backup_id. |

### API Tokens (6)

| Tool | Description |
|------|-------------|
| `npg_list_api_tokens` | List all API tokens. |
| `npg_get_api_token` | Get an API token by its ID. |
| `npg_create_api_token` | Create a new API token. Required: name, permissions (array). Optional: expires_at. |
| `npg_update_api_token` | Update an API token. Pass only fields to change (dict). |
| `npg_revoke_api_token` | Revoke an API token by its ID. |
| `npg_delete_api_token` | Delete an API token by its ID. |


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
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

This server exposes **280 MCP tools** across 27 categories. Tool names, descriptions, and full input parameter schemas are in [`tool-schemas.yaml`](tool-schemas.yaml).

| Category | Tools |
|----------|-------|
| **Proxy Hosts** | 34 tools |
| **Logs** | 32 tools |
| **Security & WAF** | 27 tools |
| **DNS Providers** | 15 tools |
| **Authentication** | 14 tools |
| **Certificates** | 15 tools |
| **Filter Subscriptions** | 14 tools |
| **Cloud Providers** | 13 tools |
| **URI Block** | 10 tools |
| **Settings** | 11 tools |
| **Backups** | 8 tools |
| **API Tokens** | 8 tools |
| **Users** | 8 tools |
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
  main.py       # All 280 MCP tools
  client.py     # HTTP client wrapper with auto-auth
  __init__.py
Dockerfile      # Multi-stage Docker build
docker-compose.yml
pyproject.toml  # Dependencies: mcp>=1.0, httpx>=0.27
tool-schemas.yaml  # Full input parameter schemas for all 280 tools
```

## License

MIT

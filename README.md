# NPG MCP Server

**English** | [한국어](README.ko.md)

MCP server for [NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard) (NPG) — manage proxy hosts, certificates, SSL, security rules, and nginx configuration through MCP tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org/).

> **⚠️ Vibe-coded with an AI agent.** This codebase was generated at speed by an AI agent, not hand-crafted by a human. Expect rough edges, unhandled edge cases, and bugs. Do **not** deploy it to an active/production NginxProxyGuard instance without first testing against a **sandboxed / disposable NPG environment** and reviewing the code. It can create, update, delete, and reconfigure live proxy hosts, so verify in isolation before pointing it at real infrastructure.

> **🤖 Automatically managed.** This codebase is continuously maintained by an autonomous coding agent via an automated kanban pipeline. Issues and pull requests submitted to this repository will be reviewed and addressed automatically.

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
# then edit .env with your NPG API token
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
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=5)"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s

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
- **Security first:** only expose the MCP endpoint to trusted networks. If you must expose it publicly, set `MCP_API_TOKEN` and keep `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS` scoped (see §Environment Variables).

## Tools Reference

This server exposes **284 MCP tools** across 27 categories. Tool names, descriptions, and full input parameter schemas are in [`tool-schemas.yaml`](tool-schemas.yaml).

| Category | Tools |
|----------|-------|
| **Proxy Hosts** | 39 tools |
| **Logs** | 32 tools |
| **Security & WAF** | 27 tools |
| **DNS Providers** | 15 tools |
| **Authentication** | 9 tools |
| **Certificates** | 15 tools |
| **Filter Subscriptions** | 14 tools |
| **Cloud Providers** | 13 tools |
| **URI Block** | 6 tools |
| **Settings** | 11 tools |
| **Backups** | 8 tools |
| **API Tokens** | 8 tools |
| **Users** | 9 tools |
| **SSO Providers** | 8 tools |
| **Dashboard** | 3 tools |
| **IP Management** | 4 tools |
| **Notification Channels** | 7 tools |
| **Redirect Hosts** | 6 tools |
| **Access Lists** | 5 tools |
| **Geo** | 10 tools |
| **Fail2ban & Challenge** | 3 tools |
| **Banned IPs & Bots** | 7 tools |
| **Roles** | 4 tools |
| **System** | 15 tools |
| **SSL / Nginx** | 4 tools |
| **System & Health** | 1 tool |
| **Docker** | 1 tool |

## Authentication

The server authenticates to NPG using a long-lived API token (`ng_...` format), set via the `NPG_API_TOKEN` environment variable. Create one in the NPG web UI or via `POST /api/v1/api-tokens`. The token is immune to password changes and is the only authentication method supported.

Session-only endpoints (account password changes, 2FA management, account metadata) are not supported — those operations require a browser session and are intentionally excluded for security.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NPG_BASE_URL` | `http://npg-api:8080` | NPG API base URL |
| `NPG_API_TOKEN` | — | NPG API token (`ng_...` format). **Required.** Create one in the NPG web UI or via `POST /api/v1/api-tokens`. |
| `MCP_PORT` | `8081` | MCP server listening port |
| `MCP_HOST` | `0.0.0.0` | MCP server bind host |
| `MCP_API_TOKEN` | *(empty)* | Bearer token required on the MCP endpoint. **Leave empty for open (local/LAN-only) mode.** Generate with `openssl rand -hex 32`. |
| `MCP_ALLOWED_HOSTS` | `localhost:port` | Comma-separated `host:port` whose `Host` header the endpoint accepts |
| `MCP_ALLOWED_ORIGINS` | *(empty)* | Comma-separated origins accepted for cross-origin requests; restricts CSRF |
| `MCP_REBINDING_PROTECTION` | `true` | Enable DNS-rebinding protection (disable only if it breaks your proxy) |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` for network deployment, `stdio` for direct pipe. Docker images default to `http`. |
| `NPG_LOG_LEVEL` | `INFO` | Container log verbosity (`DEBUG`/`INFO`/`WARNING`/`ERROR`). `INFO` logs one line per inbound MCP request and per outbound NPG API call — see Container Logs below. |
| `NPG_TOOL_LEVEL` | `full` | Layered toolset exposure: `read` (130 read-only tools), `standard` (236 tools, no destructive ops), `full` (all 284 tools). Read tools are named `npg_get_*`/`npg_list_*`/`npg_view_*`/`npg_download_*`/`npg_check_*`/`npg_detect_*`. Hidden tools are not listed and not callable. See Toolset Levels below. |

### Container Logs

`docker logs npg-mcp -f` shows what requests and errors the server is getting. At the default `INFO` level you get:

- `MCP request POST /mcp tool=npg_get_proxy_host req=r-1a2b3c4d client=192.168.1.50 -> 200 (12 ms)` — every inbound MCP request: HTTP method/path, JSON-RPC method, extracted tool name, per-request correlation ID, client IP, response status, duration.
- `NPG GET /api/v1/proxy-hosts/{id} -> 200 (8 ms) req=r-1a2b3c4d` — every outbound NPG API call: HTTP method, endpoint path, status, duration. The `req=` correlation ID matches the inbound line above, so you can tell which NPG calls belong to which MCP request even with concurrent clients.
- `NPG GET /api/v1/proxy-hosts/{id} -> HTTP 404 (3 ms)` (ERROR level) — NPG API errors (`4xx`/`5xx`). The path of the failing call lets you pin down which tool failed.
- A traceback at ERROR level for any unhandled MCP request error.

The `req=` ID (`r-<8 hex chars>`) is generated fresh per inbound request, shared by the request's inbound and outbound log lines, and appears only in logs — never in API responses or tool results. Log lines outside a request (startup, stdio mode) have no `req=` field, so existing log parsers keep working.

Set `NPG_LOG_LEVEL=DEBUG` for finer-grained output. **Tokens are never logged** — at the default level, request/response bodies aren't logged either (only endpoint paths, which map 1:1 to MCP tools). DEBUG surfaces library-level detail that may include payloads, so use it only when debugging.

### Toolset Levels

`NPG_TOOL_LEVEL` controls how much of the tool surface an MCP client sees. It is read once at server startup; hidden tools are removed from the tool manager, so they are not listed in `tools/list` and calling them returns `Unknown tool`.

| Level | Tools | Scope |
|-------|-------|-------|
| `read` | 130 | Strictly read-only tools only (`npg_get_*`, `npg_list_*`, `npg_view_*`, `npg_download_*`, `npg_check_*`, `npg_detect_*`). Suitable for monitoring agents that must not mutate NPG state. |
| `standard` | 236 | Everything except destructive operations (all deletes/removes, IP bans, backup restore/upload, password/role/email changes, token revocation, cleanup, reset, session termination, log rotation). Suitable for everyday admin work. |
| `full` | 283 | All tools. Default; behavior without the variable is unchanged. |

Anything else (or unset) falls back to `full`. `tool-schemas.yaml` always documents the full 283-tool reference regardless of the selected level.

## Project Structure

```
npg_mcp/
  main.py       # All 284 MCP tools
  client.py     # HTTP client wrapper with API token auth
  toolsets.py   # Layered toolset exposure (NPG_TOOL_LEVEL: read/standard/full)
  __init__.py
Dockerfile      # Multi-stage Docker build
docker-compose.yml
pyproject.toml  # Dependencies: mcp>=1.0, httpx>=0.27
tool-schemas.yaml  # Full input parameter schemas for all 284 tools
```

## License

MIT

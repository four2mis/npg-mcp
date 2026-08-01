# NPG MCP Server

MCP server for [NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard) (NPG) — manage proxy hosts, certificates, SSL, security rules, and nginx configuration through MCP tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org/).

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
    environment:
      - NPG_BASE_URL=http://npg-api:8080
      - NPG_USERNAME=${NPG_USERNAME}
      - NPG_PASSWORD=${NPG_PASSWORD}
      - MCP_PORT=8081
    ports:
      - "8081:8081"

networks:
  npg-network:
    external: true
```

### Hermes MCP Config

```yaml
mcp_servers:
  npg-mcp:
    url: http://<host>:8081/mcp
    connect_timeout: 30
```

## Authentication

The server **auto-authenticates** on first use using `NPG_USERNAME` and `NPG_PASSWORD`. No manual token management needed — every tool call automatically refreshes auth.

Alternatively, call `npg_auth_login` directly for explicit authentication.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NPG_BASE_URL` | `http://npg-api:8080` | NPG API base URL |
| `NPG_USERNAME` | — | NPG login username (required) |
| `NPG_PASSWORD` | — | NPG login password (required) |
| `MCP_PORT` | `8081` | MCP server listening port |

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
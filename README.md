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

Run in stdio mode — the package does **not** auto-load `.env` (that file is consumed by Docker Compose's `env_file:`), so export the variables first, or let your MCP client pass them via its `env` mapping (see Local stdio below):

```bash
set -a; source .env; set +a
python3 -m npg_mcp.main
```

### Docker Deployment (pre-built)

Pull the image from GitHub Container Registry:

```bash
docker pull ghcr.io/four2mis/npg-mcp:latest
```

Images are also tagged per release version (without the `v` prefix — releases follow a `1.0.x` scheme):

```bash
docker pull ghcr.io/four2mis/npg-mcp:1.0.0
```

Images are published as **multi-arch manifests (linux/amd64 + linux/arm64)** — `docker pull` selects the right platform automatically.

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
    # All runtime config comes from .env (see .env.example). Copy .env.example to
    # .env and fill in your values. No secrets in this file.
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

Tools then appear as `mcp__npg_mcp__*` — the MCP server key `npg-mcp` is sanitized to `npg_mcp` (e.g. `mcp__npg_mcp__npg_list_proxy_hosts`).

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

### Local stdio (no HTTP server)

When launched as a plain process the server defaults to `MCP_TRANSPORT=stdio` — no port, no `MCP_API_TOKEN`; the MCP client starts the process itself and talks over stdin/stdout. Point a command-server client at the venv interpreter and pass configuration through the client's `env` mapping (the package has no `.env` auto-loading):

```json
{
  "mcpServers": {
    "npg-mcp": {
      "command": "/path/to/npg-mcp/.venv/bin/python3",
      "args": ["-m", "npg_mcp.main"],
      "env": {
        "NPG_BASE_URL": "http://<npg-api-host>:8080",
        "NPG_API_TOKEN": "ng_..."
      }
    }
  }
}
```

`MCP_TRANSPORT` doesn't need to be set — stdio is the bare-process default. Hermes uses the same stdio keys:

```yaml
mcp_servers:
  npg-mcp:
    command: /path/to/npg-mcp/.venv/bin/python3
    args: ["-m", "npg_mcp.main"]
    env:
      NPG_BASE_URL: http://<npg-api-host>:8080
      NPG_API_TOKEN: ng_...
```

`MCP_API_TOKEN` does not apply over stdio — access control is whoever can execute the process.

### Network & Firewall Notes

- The server listens on `MCP_PORT` (default `8081`) bound to `MCP_HOST` (default `0.0.0.0`).
- **DNS-rebinding protection** (`MCP_REBINDING_PROTECTION=true` by default) rejects requests whose `Host` header isn't in `MCP_ALLOWED_HOSTS`. If clients connect by hostname/IP not covered by the default (`localhost:8081,127.0.0.1:8081`), add it to `MCP_ALLOWED_HOSTS` in `.env`, e.g. `MCP_ALLOWED_HOSTS=127.0.0.1:8081,mynas.local:8081,192.168.1.50:8081`.
- **Security first:** only expose the MCP endpoint to trusted networks. If you must expose it publicly, set `MCP_API_TOKEN` and keep `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS` scoped (see §Environment Variables).

## Tools Reference

This server exposes **313 MCP tools** across 29 categories. Tool names, descriptions, and full input parameter schemas are in [`tool-schemas.yaml`](tool-schemas.yaml).

| Category | Tools |
|----------|-------|
| **Proxy Hosts** | 46 tools |
| **Logs** | 38 tools |
| **Security & WAF** | 31 tools |
| **DNS Providers** | 15 tools |
| **Authentication** | 9 tools |
| **Certificates** | 15 tools |
| **Filter Subscriptions** | 15 tools |
| **Cloud Providers** | 13 tools |
| **URI Block** | 7 tools |
| **Settings** | 12 tools |
| **Backups** | 8 tools |
| **API Tokens** | 8 tools |
| **Users** | 9 tools |
| **SSO Providers** | 8 tools |
| **Other** | 2 tools |
| **Dashboard** | 3 tools |
| **Traffic** | 4 tools |
| **IP Management** | 4 tools |
| **Notification Channels** | 7 tools |
| **Redirect Hosts** | 6 tools |
| **Access Lists** | 6 tools |
| **Geo** | 11 tools |
| **Fail2ban & Challenge** | 3 tools |
| **Banned IPs & Bots** | 7 tools |
| **Roles** | 4 tools |
| **System** | 18 tools |
| **SSL / Nginx** | 2 tools |
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
| `MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` for direct pipes (bare-process default), `http` for network deployment. Docker images set `http` via `ENV`. |
| `NPG_LOG_LEVEL` | `INFO` | Container log verbosity (`DEBUG`/`INFO`/`WARNING`/`ERROR`). `INFO` logs one line per inbound MCP request and per outbound NPG API call — see Container Logs below. |
| `NPG_TOOL_LEVEL` | `full` | Layered toolset exposure: `read` (141 read-only tools), `standard` (266 tools, no destructive ops), `full` (all 313 tools). Read tools are named `npg_get_*`/`npg_list_*`/`npg_view_*`/`npg_download_*`/`npg_check_*`/`npg_detect_*`, except three probes that write or POST (`npg_check_log_archive`, `npg_detect_telegram_chats`, `npg_check_backup_restore`), which stay at `standard`/`full` only. Hidden tools are not listed and not callable. See Toolset Levels below. |
| `NPG_TOOL_SCOPE_FILTER` | `0` | Opt-in scope-aware tool filtering. When enabled, the server discovers the configured `NPG_API_TOKEN`'s effective permissions **once at boot** — `GET /api/v1/api-tokens` (needs `apitoken:read`) with a prefixed-row match, falling back to `GET /api/v1/auth/me` — and exposes only the tools those scopes cover: `NPG_TOOL_LEVEL` ∩ granted scopes. Scopes match by exact string (`*` and `area:*` wildcards allowed), so legacy scopes are not widened. Restart to pick up a scope change. Fails **open**: both endpoints failing (403/timeout), no or ambiguous token-prefix match, or an unset token leaves the full manifest in place, and unannotated tools are never hidden. Off by default — the manifest and tool count are then unchanged. See Scope Filtering below. |
| `NPG_DRY_RUN` | `0` | Dry-run safety mode: when set to a truthy value (`1`/`true`/`on`), every mutating tool returns the exact request it WOULD send (`{"dry_run": true, "method", "path", "body", ...}`) instead of executing — nothing is applied. Rehearse a first deployment against a live instance before switching it off. |
| `NPG_HTTP_TIMEOUT` | `30` | Outbound NPG API request timeout in seconds. Raise it for endpoints that legitimately run long (large access-log downloads, backup export/restore, certificate upload, full proxy-host syncs) to avoid `ReadTimeout` failures. Clamped to `[1, 600]`; invalid values fall back to `30` with a warning. |
| `NPG_MAX_RESULT_CHARS` | `65536` | Ceiling on the serialized size (compact JSON characters) of any read/list/get tool result. Over-budget payloads are truncated at data boundaries only and carry a `truncated` metadata object; `expand=true` on the call lifts the cap. Clamped to `[1024, 8000000]`; invalid values fall back to `65536` with a warning. See Result Envelope & Truncation below. |

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
| `read` | 141 | Strictly read-only tools only (`npg_get_*`, `npg_list_*`, `npg_view_*`, `npg_download_*`, `npg_check_*`, `npg_detect_*`), minus three probing tools that write or use a POST body (`npg_check_log_archive`, `npg_detect_telegram_chats`, `npg_check_backup_restore`) — those stay at `standard`/`full`. Suitable for monitoring agents that must not mutate NPG state. |
| `standard` | 266 | Everything except destructive operations (all deletes/removes, IP bans, backup restore/upload, password/role/email changes, token revocation, cleanup, reset, session termination, log rotation). Suitable for everyday admin work. |
| `full` | 313 | All tools. Default; behavior without the variable is unchanged. |

Anything else (or unset) falls back to `full`. `tool-schemas.yaml` always documents the full 313-tool reference regardless of the selected level.

### Scope Filtering

`NPG_TOOL_SCOPE_FILTER` (default `0`, off) narrows the surface one step further: with it enabled the server exposes only the tools the configured `NPG_API_TOKEN` can actually call. Useful when the MCP endpoint is handed a scoped token — a monitoring token holding `read_only` scopes does not need the write tools it would only ever get `403`s from.

It resolves the grant **once at boot**, from two endpoints in order:

1. `GET /api/v1/api-tokens` — the token rows, each with its displayable `token_prefix` (`ng_` + the first 8 characters) and its `permissions` array (`*` or entries from NPG's 15 legacy resource scopes). Match the row whose `token_prefix` the configured token starts with.
2. Fallback `GET /api/v1/auth/me` — a self-service route needing no permission. It reports `effective_permissions` for a token caller: the owner role's permissions intersected with the token's own scopes, i.e. exactly what NPG enforces per request. (This fallback matters in practice: a UI-created token can only carry `*` or the legacy scopes, and NPG checks token scopes by exact string, so a scoped token always gets `403` on `/api/v1/api-tokens`.)

Matching mirrors NPG's `APIToken.HasPermission` exactly: a tool is exposed when **every** permission its routes need is covered by `*`, by the identical string, or by an `area:*` family wildcard. Legacy scopes are **not** widened into other areas and `write` does not imply `read` — that expansion applies to *roles*, not tokens (verified against NPG 2.65.4: a `read_only` token reaches exactly proxy/certificate/waf/logs/settings/backup reads and `403`s on redirect/access/authprovider/dnsprovider/ddns/audit/dashboard/user/role). The exposed set is `NPG_TOOL_LEVEL` ∩ `{tools whose every required permission is granted}`.

Because the snapshot happens at boot, **changing the token's scopes in the NPG UI needs an MCP restart** to change the surface. The boot log records what it saw, and `npg_get_stack_features` returns the same information as data:

```json
"hidden_by_scope": {
  "enabled": true, "applied": true, "reason": "", "snapshot": "boot",
  "source": "/api/v1/auth/me",
  "token_prefix": "ng_c9233b0e",
  "stored_permissions": ["proxy:read", "waf:read", "settings:read"],
  "granted_scope_count": 3,
  "hidden_count": 231, "hidden_tools": ["npg_ban_ip", "..."],
  "exposed_count": 78, "manifest_before": 309,
  "unmapped_tool_count": 0
}
```

`hidden_by_scope` is `null` when the filter is off; `npg_get_stack_features` itself is never hidden by it, so a restricted server can always report what it hid.

**It fails open, always.** Hiding a tool that would have worked is worse than showing one that answers `403` — a hidden `npg_create_*` removes the only path that makes a feature exist. Every uncertainty therefore keeps the full tier manifest: both introspection endpoints failing (`403`, timeout, transport error), no row matching the token prefix, more than one matching row (ambiguity), an unset `NPG_API_TOKEN`, or an empty/unparseable permissions array. The reason is logged at `WARNING` and returned in `hidden_by_scope.reason`. Tools that carry no permission annotation are also never hidden, so a freshly bridged upstream endpoint cannot disappear silently.

The tool → permission map lives in `npg_mcp/permission_map.py`, generated by `scripts/derive_tool_permissions.py` from NPG's own route-authorisation registry (`api/internal/middleware/permissions.go`); `tests/test_scopefilter.py` fails when a registered tool is missing from it, so the map cannot fall behind the tool surface. With the filter off, the manifest, the tool count and the tier counts above are exactly what they are without it.

### Tool Annotations

Every tool is served with standard MCP `ToolAnnotations` — `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` — plus a derived human-readable `title`. They are computed at startup from the HTTP verbs each tool's body calls plus the destructive-name registry behind the toolset levels, so the hints cannot drift from the code and never change tool behavior:

| Hint | `true` for |
|------|-----------|
| `readOnlyHint` | Tools whose only NPG calls are GETs (`npg_get_*`, `npg_list_*`, `npg_download_*`, …). One GET probe is deliberately `false`: `npg_check_backup_restore` writes and deletes a throwaway backup row. |
| `destructiveHint` | The destructive set hidden at the `standard` level: deletes, removes, IP bans, resets, restores, revocations, credential changes, session termination, log rotation. |
| `idempotentHint` | GET-only tools and idempotent `PUT` updates — repeating the call reaches the same end state. Creates, tests, and deletes are `false`. |
| `openWorldHint` | `false` only for closed-catalog reads (countries, presets, permission areas, known bots, WAF test patterns, log sources/levels, audit-log actions); `true` everywhere else, since the API reaches upstreams, ACME, DNS providers, and Telegram. |

### Result Envelope & Truncation

Every tool answers with the same envelope: `{"success": true, "data": <payload>}` (plus the tool's own extras such as `message`, `encoding` or paging keys). Failures return `{"success": false, "error": "...", "hint": "..."}` — always check the nested `success` field, not just the JSON-RPC `isError` flag.

**Result cap.** No single read/list/get result may exceed `NPG_MAX_RESULT_CHARS` (default `65536`) characters of compact JSON. A larger payload is truncated **at data boundaries only** — trailing array items are dropped and oversized string values are clamped with an `... [clamped N chars]` marker — and a `truncated` object is added next to `data`:

| Field | Meaning |
|-------|---------|
| `total_chars` | size of the untruncated result (compact JSON characters) |
| `returned_chars` | size of what was actually returned, `truncated` object included |
| `omitted_items` | trailing array items dropped from the payload |
| `clamped_strings` | number of string values shortened by the clamp marker |
| `hint` | how to get the rest — names the exact narrower parameters this tool really has (`limit`/`offset`/`sections`/`lines`), or points at `expand=true` when it has none |

Truncation never cuts mid-structure or mid-string: the envelope is rebuilt from a reduced object, so what a client receives is always complete, parseable JSON. Results at or under the cap are returned byte-for-byte unchanged and carry no `truncated` key.

**Escape hatch.** Every capped tool accepts `expand: bool = False`. Passing `expand=true` lifts the cap for that one call and returns the complete payload — use it for one-off downloads (`npg_download_backup`, `npg_get_certificate_download`), where a shortened base64 payload cannot be decoded. `npg_download_log_file` keeps its own 256 KB cap (`truncated: true`, `total_bytes`, `returned_bytes`, `hint` → `npg_view_log_file`) instead of the generic one.

## Project Structure

```
npg_mcp/
  main.py       # All 313 MCP tools
  client.py     # HTTP client wrapper with API token auth
  toolsets.py   # Toolset levels (NPG_TOOL_LEVEL: read/standard/full) + MCP ToolAnnotations
  resultcap.py  # Shared result cap (NPG_MAX_RESULT_CHARS) + `expand` escape hatch
  scopefilter.py    # Opt-in scope-aware narrowing (NPG_TOOL_SCOPE_FILTER)
  permission_map.py # Generated tool → NPG permission map for the scope filter
  __init__.py
Dockerfile      # Multi-stage Docker build
docker-compose.yml
pyproject.toml  # Dependencies: mcp>=1.29.0,<2.0.0, httpx>=0.27.0
tool-schemas.yaml  # Full input parameter schemas for all 313 tools
```

## Development & Testing

```bash
pytest tests/ -q   # offline — NPG API calls are mocked (respx); no live instance needed
```

Documentation (`tool-schemas.yaml`, both READMEs) is generated from the tool surface and must stay in sync — the format contract lives in [AGENTS.md](AGENTS.md). Release history: [CHANGELOG.md](CHANGELOG.md).

## License

MIT

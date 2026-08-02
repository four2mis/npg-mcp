# NPG MCP 서버

[English](README.md) | **한국어**

[NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard)(NPG)용 MCP 서버 — MCP 도구를 통해 프록시 호스트, 인증서, SSL, 보안 규칙, nginx 구성을 관리합니다.

[FastMCP](https://github.com/jlowin/fastmcp)와 [httpx](https://www.python-httpx.org/)로 구축되었습니다.

> **⚠️ AI 에이전트로 바이브 코딩(vibe-coded)되었습니다.** 이 코드베이스는 사람이 직접 작성한 것이 아니라 AI 에이전트가 빠르게 생성한 것입니다. 미세한 결함, 처리되지 않은 엣지 케이스, 버그가 있을 수 있습니다. 실제 운영 중인 NginxProxyGuard 인스턴스에 배포하기 전에 반드시 **격리된(샌드박스) NPG 환경**에서 먼저 테스트하고 코드를 검토하십시오. 이 서버는 실제 프록시 호스트를 생성·수정·삭제·재구성할 수 있으므로, 실제 인프라에 연결하기 전에 반드시 격리된 환경에서 검증하십시오.

## 기능

NPG의 모든 API 카테고리에 걸친 108+ 개의 MCP 도구:

| 카테고리 | 도구 |
|----------|-------|
| **인증(Auth)** | login, logout, me |
| **대시보드(Dashboard)** | overview, health, geoip stats |
| **프록시 호스트(Proxy Hosts)** | list, get, create, update, delete, test, clone, sync, regenerate |
| **보안(호스트별)** | rate limit, bot filter, security headers(+presets), upstream, URI block, fail2ban, challenge/CAPTCHA |
| **지역 제한(Geo Restriction)** | get, create, update, delete (per-host) |
| **인증서(Certificates)** | list, get, create, delete, renew |
| **리다이렉트 호스트(Redirect Hosts)** | list, get, create, update, delete |
| **액세스 목록(Access Lists)** | list, get, create, update, delete |
| **DNS 제공자(DNS Providers)** | list, get, create, update, delete, test |
| **클라우드 제공자(Cloud Providers)** | list, get, create, update, delete |
| **WAF** | list rules, get hosts/config, disable rules |
| **악성 규칙(Exploit Rules)** | list, get, create, update, delete, toggle |
| **설정(Settings)** | global settings, system settings, nginx sync |
| **로그(Logs)** | access logs, audit logs, system logs, stats |
| **백업(Backups)** | list, get, create, delete, restore |
| **API 토큰(API Tokens)** | list, get, create, update, revoke, delete |

## 도구 참조(Tools Reference)

이 서버는 다음 카테고리에 걸쳐 **108개의 MCP 도구**를 노출합니다:

- **인증(Auth)** (4)
- **대시보드(Dashboard)** (3)
- **프록시 호스트(Proxy Hosts)** (10)
- **SSL / Nginx** (8)
- **리다이렉트 호스트(Redirect Hosts)** (5)
- **보안(호스트별)** (12)
- **지역 제한(Geo Restriction)** (5)
- **Fail2ban & 챌린지** (6)
- **액세스 목록(Access Lists)** (5)
- **DNS 제공자(DNS Providers)** (6)
- **클라우드 제공자(Cloud Providers)** (5)
- **GeoIP** (2)
- **차단 IP & 봇(Banned IPs & Bots)** (4)
- **URI 차단(URI Block)** (2)
- **WAF & 악성 규칙(WAF & Exploit Rules)** (10)
- **설정(Settings)** (4)
- **로그(Logs)** (6)
- **백업(Backups)** (5)
- **API 토큰(API Tokens)** (6)

### 인증(Auth) (4)

| 도구 | 설명 |
|------|------|
| `npg_auth_login` | Authenticate with NPG credentials. The resulting session token is stored server-side; it is not returned to the client. |
| `npg_auth_logout` | Invalidate the current session token. |
| `npg_auth_me` | Get the current authenticated user's info. |
| `npg_change_password` | Change the current user's password. REQUIRED: current_password, new_password (min 8 chars). |

### 대시보드(Dashboard) (3)

| 도구 | 설명 |
|------|------|
| `npg_get_dashboard` | Get dashboard data (summary of proxy hosts, certificates, etc.). |
| `npg_get_dashboard_health` | Get system health status. |
| `npg_get_dashboard_geoip_stats` | GET GeoIP statistics by country for the dashboard. |

### 프록시 호스트(Proxy Hosts) (10)

| 도구 | 설명 |
|------|------|
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

| 도구 | 설명 |
|------|------|
| `npg_list_certificates` | List all SSL/TLS certificates. |
| `npg_get_certificate` | Get a certificate by its ID. |
| `npg_create_certificate` | Request a new Let's Encrypt certificate. Required: domain_names (array), email. Optional: provider (e.g. 'letsencrypt'), dns_provider_id, etc. |
| `npg_delete_certificate` | Delete a certificate by its ID. |
| `npg_renew_certificate` | Renew a certificate by its ID. |
| `npg_reload_nginx` | Reload nginx configuration without full restart. |
| `npg_sync_nginx` | Sync all configs and reload nginx. |
| `npg_test_nginx` | Test nginx configuration for validity. |

### 리다이렉트 호스트(Redirect Hosts) (5)

| 도구 | 설명 |
|------|------|
| `npg_list_redirect_hosts` | List all redirect hosts. |
| `npg_get_redirect_host` | Get a redirect host by its ID. |
| `npg_create_redirect_host` | Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, default 301). |
| `npg_update_redirect_host` | Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code. |
| `npg_delete_redirect_host` | Delete a redirect host by its ID. |

### 보안(호스트별) (12)

| 도구 | 설명 |
|------|------|
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

### 지역 제한(Geo Restriction) (5)

| 도구 | 설명 |
|------|------|
| `npg_get_proxy_host_geo` | GET geo restriction configuration for a proxy host. |
| `npg_create_proxy_host_geo` | CREATE geo restriction for a proxy host. Body: enabled, mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode |
| `npg_update_proxy_host_geo` | UPDATE geo restriction for a proxy host. Body: enabled, mode, countries, allowed_ips, challenge_mode |
| `npg_delete_proxy_host_geo` | DELETE geo restriction for a proxy host. |
| `npg_list_countries` | List available country codes for GeoIP blocking. |

### Fail2ban & 챌린지 (6)

| 도구 | 설명 |
|------|------|
| `npg_get_proxy_host_fail2ban` | GET fail2ban configuration for a proxy host. |
| `npg_update_proxy_host_fail2ban` | UPDATE fail2ban configuration. Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge) |
| `npg_get_proxy_host_challenge` | GET CAPTCHA/challenge configuration for a proxy host. |
| `npg_update_proxy_host_challenge` | UPDATE CAPTCHA/challenge configuration. Body: enabled, challenge_type (captcha/js_challenge), difficulty, site_key, token_validity, min_score, apply_to, page_title, challenge_ips |
| `npg_delete_proxy_host_challenge` | DELETE CAPTCHA/challenge configuration for a proxy host. |
| `npg_verify_challenge` | Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution. |

### 액세스 목록(Access Lists) (5)

| 도구 | 설명 |
|------|------|
| `npg_list_access_lists` | List all access lists (authentication/restriction lists). |
| `npg_get_access_list` | Get an access list by its ID. |
| `npg_create_access_list` | Create a new access list. Required: name, advanced_config (block/allow rules). |
| `npg_update_access_list` | Update an access list. Pass only fields to change. |
| `npg_delete_access_list` | Delete an access list by its ID. |

### DNS 제공자(DNS Providers) (6)

| 도구 | 설명 |
|------|------|
| `npg_list_dns_providers` | List all DNS providers configured for DNS-01 challenges. |
| `npg_get_dns_provider` | Get a DNS provider by its ID. |
| `npg_create_dns_provider` | Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}). |
| `npg_update_dns_provider` | Update a DNS provider. Pass only fields to change (dict). |
| `npg_delete_dns_provider` | Delete a DNS provider by its ID. |
| `npg_test_dns_provider` | Test DNS provider credentials. |

### 클라우드 제공자(Cloud Providers) (5)

| 도구 | 설명 |
|------|------|
| `npg_list_cloud_providers` | List all cloud providers (for certificate DNS challenges). |
| `npg_get_cloud_provider` | Get a cloud provider by its slug. |
| `npg_create_cloud_provider` | Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description. |
| `npg_update_cloud_provider` | Update a cloud provider by its slug. Pass only fields to change (dict). |
| `npg_delete_cloud_provider` | Delete a cloud provider by its slug. |

### GeoIP (2)

| 도구 | 설명 |
|------|------|
| `npg_get_geoip_status` | Get GeoIP database update status. |
| `npg_update_geoip` | Update GeoIP databases. |

### 차단 IP & 봇(Banned IPs & Bots) (4)

| 도구 | 설명 |
|------|------|
| `npg_list_banned_ips` | List banned IP addresses. |
| `npg_ban_ip` | Ban an IP address. Required: ip. Optional: ban_time (seconds). |
| `npg_unban_ip` | Unban an IP by its ID. |
| `npg_get_bots_known` | Get list of known bot user-agent signatures. |

### URI 차단(URI Block) (2)

| 도구 | 설명 |
|------|------|
| `npg_get_global_uri_block` | Get global URI block settings. |
| `npg_update_global_uri_block` | Update global URI block settings. Pass only fields to change (dict). |

### WAF & 악성 규칙(WAF & Exploit Rules) (10)

| 도구 | 설명 |
|------|------|
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

### 설정(Settings) (4)

| 도구 | 설명 |
|------|------|
| `npg_get_settings` | Get global NPG settings. |
| `npg_update_settings` | Update global NPG settings. Pass only fields to change (dict). |
| `npg_get_system_settings` | Get system settings (server name, timezone, locale). |
| `npg_update_system_settings` | Update system settings. Pass only fields to change (dict). |

### 로그(Logs) (6)

| 도구 | 설명 |
|------|------|
| `npg_get_logs` | Get access logs. |
| `npg_get_log_settings` | Get log settings. |
| `npg_update_log_settings` | Update log settings. Pass only fields to change (dict). |
| `npg_get_log_stats` | Get log statistics. |
| `npg_list_audit_logs` | List audit log entries. |
| `npg_list_system_logs` | List system logs. |

### 백업(Backups) (5)

| 도구 | 설명 |
|------|------|
| `npg_list_backups` | List all backups. |
| `npg_get_backup` | Get a backup by its ID. |
| `npg_create_backup` | Create a new backup. |
| `npg_delete_backup` | Delete a backup by its ID. |
| `npg_restore_backup` | Restore from a backup. Required: backup_id. |

### API 토큰(API Tokens) (6)

| 도구 | 설명 |
|------|------|
| `npg_list_api_tokens` | List all API tokens. |
| `npg_get_api_token` | Get an API token by its ID. |
| `npg_create_api_token` | Create a new API token. Required: name, permissions (array). Optional: expires_at. |
| `npg_update_api_token` | Update an API token. Pass only fields to change (dict). |
| `npg_revoke_api_token` | Revoke an API token by its ID. |
| `npg_delete_api_token` | Delete an API token by its ID. |


## 빠른 시작

### 사전 요구 사항

- API 접근이 가능한 실행 중인 NginxProxyGuard(NPG) 인스턴스
- Docker 및 Docker Compose(컨테이너 배포용)
- Python 3.11+(로컬 개발용)

### 로컬 개발

```bash
git clone https://github.com/four2mis/npg-mcp.git
cd npg-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

`.env` 파일 생성(`.env.example`에서 복사):

```bash
cp .env.example .env
```

stdio 모드로 실행:

```bash
python3 -m npg_mcp.main
```

### Docker 배포(사전 빌드)

GitHub Container Registry에서 이미지 가져오기:

```bash
docker pull ghcr.io/four2mis/npg-mcp:latest
```

템플릿에서 `.env` 파일 생성:

```bash
cp .env.example .env
# 그리고 .env를 NPG 자격 증명으로 편집
```

또는 포함된 `docker-compose.yml`로 Docker Compose 실행:

```bash
# 가져와서 실행(사전 빌드 이미지 사용)
docker compose up -d

# 또는 소스에서 빌드
docker compose up -d --build
```

포함된 `docker-compose.yml`:

```yaml
services:
  npg-mcp:
    image: ghcr.io/four2mis/npg-mcp:latest
    # build: .  # 주석을 해제하면 소스에서 빌드
    container_name: npg-mcp
    restart: unless-stopped
    networks:
      - npg-network
    # 모든 런타임 설정은 .env에서 가져옵니다(.env.example 참고). 여기에 시크릿 없음.
    env_file:
      - .env
    ports:
      - "8081:8081"

networks:
  npg-network:
    external: true
```

## MCP 클라이언트에 연결

서버를 배포하면(위 Docker 섹션 참조) MCP 엔드포인트가 `http://<host>:8081/mcp`에 게시됩니다. MCP를 지원하는 모든 에이전트에서 이 URL을 가리키면 사용할 수 있습니다.

> **`MCP_API_TOKEN`이 설정된 경우(네트워크에 노출된 모든 배포에서 권장), 모든 MCP 요청은 `Authorization: Bearer <MCP_API_TOKEN>` 헤더를 반드시 포함해야 합니다** — 없으면 `401`이 반환됩니다. 아래 각 클라이언트 설정에서 헤더를 어디에 넣는지 보여줍니다. 토큰(`openssl rand -hex 32`)은 서버의 `.env`에 `MCP_API_TOKEN`으로 설정됩니다.

### Hermes 에이전트

`~/.hermes/config.yaml`의 `mcp_servers` 아래에 추가한 뒤 Hermes를 재시작하십시오(MCP 서버는 시작 시에만 탐색되며 핫-리로드가 없습니다):

```yaml
mcp_servers:
  npg-mcp:
    url: http://<host>:8081/mcp
    connect_timeout: 30
    headers:
      Authorization: "Bearer <MCP_API_TOKEN>"
```

또는 설정을 직접 편집하지 않고 CLI로 설정:

```bash
hermes config set mcp_servers.npg-mcp.url 'http://<host>:8081/mcp'
hermes config set mcp_servers.npg-mcp.headers.Authorization 'Bearer <MCP_API_TOKEN>'
```

그러면 도구가 `mcp_npg_mcp_*`로 나타납니다(예: `mcp_npg_mcp_npg_list_proxy_hosts`).

### Claude Code / Claude Desktop

Claude MCP 설정에 추가(Claude Desktop: `claude_desktop_config.json`);
Claude Code: `~/.claude.json` — `mcpServers` 키 또는 `claude mcp add`):

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

`~/.codex/config.toml`의 `[mcp_servers.npg-mcp]` 아래에 추가:

```toml
[mcp_servers.npg-mcp]
url = "http://<host>:8081/mcp"
headers = { Authorization = "Bearer <MCP_API_TOKEN>" }
```

### Cursor / VS Code / 기타 MCP 클라이언트

클라이언트의 MCP 설정에 **원격 / SSE+HTTP MCP 서버** 항목을 추가하십시오:

- **URL:** `http://<host>:8081/mcp`
- **헤더:** `Authorization: Bearer <MCP_API_TOKEN>`(토큰이 설정된 경우)

Streamable HTTP 서버(`type: "http"` / `sse`)를 지원하는 모든 MCP 클라이언트가 연결할 수 있습니다. 이 엔드포인트는 표준 FastMCP Streamable HTTP 서버입니다.

### 네트워크 및 방화벽 참고 사항

- 서버는 `MCP_PORT`(기본값 `8081`)에서 수신하며 `MCP_HOST`(기본값 `0.0.0.0`)에 바인딩됩니다.
- **DNS 리바인딩 보호**(기본적으로 `MCP_REBINDING_PROTECTION=true`)는 `MCP_ALLOWED_HOSTS`에 없는 `Host` 헤더의 요청을 거부합니다. 기본값(`localhost:8081,127.0.0.1:8081`)에 포함되지 않은 호스트명/IP로 클라이언트가 접속하는 경우 `.env`의 `MCP_ALLOWED_HOSTS`에 추가하십시오. 예: `MCP_ALLOWED_HOSTS=127.0.0.1:8081,mynas.local:8081,192.168.1.50:8081`.
- **보안 우선:** 신뢰할 수 있는 네트워크에만 MCP 엔드포인트를 노출하십시오. 공개적으로 노출해야 한다면 `MCP_API_TOKEN`을 설정하고 `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS`를 좁게 유지하십시오(README §환경 변수).

## 인증

서버는 `NPG_USERNAME`과 `NPG_PASSWORD`를 사용해 **첫 사용 시 자동 인증**합니다. 수동 토큰 관리가 필요 없습니다 — 모든 도구 호출이 인증을 자동으로 갱신합니다.

또는 명시적 인증을 위해 `npg_auth_login`을 직접 호출할 수 있습니다. 생성된 NPG 세션 토큰은 **서버 측에만 저장**되며 클라이언트에 반환되지 않습니다.

## 환경 변수

| 변수 | 기본값 | 설명 |
|----------|---------|-------------|
| `NPG_BASE_URL` | `http://npg-api:8080` | NPG API 기본 URL |
| `NPG_USERNAME` | — | NPG 로그인 사용자 이름(필수) |
| `NPG_PASSWORD` | — | NPG 로그인 비밀번호(필수) |
| `MCP_PORT` | `8081` | MCP 서버 수신 포트 |
| `MCP_HOST` | `0.0.0.0` | MCP 서버 바인딩 호스트 |
| `MCP_API_TOKEN` | *(비어 있음)* | MCP 엔드포인트에 필요한 Bearer 토큰. **열린(로컬/LAN 전용) 모드로 하려면 비워 두십시오.** `openssl rand -hex 32`로 생성. |
| `MCP_ALLOWED_HOSTS` | `localhost:port` | 엔드포인트가 허용하는 `Host` 헤더의 `host:port`(쉼표 구분, 예: 리버스 프록시 공개 호스트) |
| `MCP_ALLOWED_ORIGINS` | *(비어 있음)* | 교차 출처 요청에서 허용되는 origin(쉼표 구분); CSRF 제한 |
| `MCP_REBINDING_PROTECTION` | `true` | DNS 리바인딩 보호 활성화(프록시가 깨지는 경우에만 비활성화) |

## 프로젝트 구조

```
npg_mcp/
  main.py       # 108+ 개의 모든 MCP 도구
  client.py     # 자동 인증을 갖춘 HTTP 클라이언트 래퍼
  __init__.py
Dockerfile      # Multi-stage Docker 빌드
docker-compose.yml
pyproject.toml  # 의존성: mcp>=1.0, httpx>=0.27
```

## 라이선스

MIT

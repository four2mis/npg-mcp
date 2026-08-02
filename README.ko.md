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

# NPG MCP 서버

[English](README.md) | **한국어**

[NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard)(NPG)용 MCP 서버 — MCP 도구를 통해 프록시 호스트, 인증서, SSL, 보안 규칙, nginx 구성을 관리합니다.

[FastMCP](https://github.com/jlowin/fastmcp)와 [httpx](https://www.python-httpx.org/)로 구축되었습니다.

> **⚠️ AI 에이전트로 바이브 코딩(vibe-coded)되었습니다.** 이 코드베이스는 사람이 직접 작성한 것이 아니라 AI 에이전트가 빠르게 생성한 것입니다. 미세한 결함, 처리되지 않은 엣지 케이스, 버그가 있을 수 있습니다. 실제 운영 중인 NginxProxyGuard 인스턴스에 배포하기 전에 반드시 **격리된(샌드박스) NPG 환경**에서 먼저 테스트하고 코드를 검토하십시오. 이 서버는 실제 프록시 호스트를 생성·수정·삭제·재구성할 수 있으므로, 실제 인프라에 연결하기 전에 반드시 격리된 환경에서 검증하십시오.

> **🤖 자동 관리.** 이 코드베이스는 자동화된 칸반 파이프라인을 통해 자율 코딩 에이전트가 지속적으로 관리합니다. 이 저장소에 제출된 이슈 및 풀 리퀘스트는 자동으로 검토 및 처리됩니다.

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
# 그리고 .env를 NPG API 토큰으로 편집
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
- **헤더:** `Authorization: Bearer <MCP_API_TOKEN>` (토큰이 설정된 경우)

Streamable HTTP 서버(`type: "http"` / `sse`)를 지원하는 모든 MCP 클라이언트가 연결할 수 있습니다. 이 엔드포인트는 표준 FastMCP Streamable HTTP 서버입니다.

### 네트워크 및 방화벽 참고 사항

- 서버는 `MCP_PORT`(기본값 `8081`)에서 수신하며 `MCP_HOST`(기본값 `0.0.0.0`)에 바인딩됩니다.
- **DNS 리바인딩 보호**(기본적으로 `MCP_REBINDING_PROTECTION=true`)는 `MCP_ALLOWED_HOSTS`에 없는 `Host` 헤더의 요청을 거부합니다. 기본값(`localhost:8081,127.0.0.1:8081`)에 포함되지 않은 호스트명/IP로 클라이언트가 접속하는 경우 `.env`의 `MCP_ALLOWED_HOSTS`에 추가하십시오. 예: `MCP_ALLOWED_HOSTS=127.0.0.1:8081,mynas.local:8081,192.168.1.50:8081`.
- **보안 우선:** 신뢰할 수 있는 네트워크에만 MCP 엔드포인트를 노출하십시오. 공개적으로 노출해야 한다면 `MCP_API_TOKEN`을 설정하고 `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS`를 좁게 유지하십시오(README §환경 변수).

## 도구 참조(Tools Reference)

이 서버는 **280개의 MCP 도구**를 27개 카테고리에 걸쳐 노출합니다. 전체 도구 이름, 설명, 입력 매개변수 스키마는 [`tool-schemas.yaml`](tool-schemas.yaml)에 있습니다.

| 카테고리 | 도구 |
|----------|-------|
| **프록시 호스트(Proxy Hosts)** | 38 tools |
| **로그(Logs)** | 32 tools |
| **보안 및 WAF(Security & WAF)** | 27 tools |
| **DNS 제공자(DNS Providers)** | 15 tools |
| **인증(Authentication)** | 9 tools |
| **인증서(Certificates)** | 15 tools |
| **필터 구독(Filter Subscriptions)** | 14 tools |
| **클라우드 제공자(Cloud Providers)** | 13 tools |
| **URI 차단(URI Block)** | 6 tools |
| **설정(Settings)** | 11 tools |
| **백업(Backups)** | 8 tools |
| **API 토큰(API Tokens)** | 8 tools |
| **사용자(Users)** | 9 tools |
| **SSO 제공자(SSO Providers)** | 8 tools |
| **대시보드(Dashboard)** | 3 tools |
| **IP 관리(IP Management)** | 4 tools |
| **알림 채널(Notification Channels)** | 8 tools |
| **리다이렉트 호스트(Redirect Hosts)** | 6 tools |
| **액세스 목록(Access Lists)** | 5 tools |
| **지역(Geo)** | 10 tools |
| **Fail2ban 및 챌린지(Fail2ban & Challenge)** | 3 tools |
| **차단 IP 및 봇(Banned IPs & Bots)** | 7 tools |
| **역할(Roles)** | 4 tools |
| **시스템(System)** | 12 tools |
| **SSL / Nginx** | 3 tools |
| **시스템 및 상태(System & Health)** | 1 tool |
| **Docker** | 1 tool |

## 인증

서버는 장기 API 토큰(`ng_...` 형식)을 사용하여 NPG에 인증하며, `NPG_API_TOKEN` 환경 변수로 설정합니다. NPG 웹 UI 또는 `POST /api/v1/api-tokens`에서 토큰을 생성하십시오. 이 토큰은 비밀번호 변경에 영향을 받지 않으며, 유일하게 지원되는 인증 방법입니다.

세션 전용 엔드포인트(계정 비밀번호 변경, 2FA 관리, 계정 메타데이터)는 지원되지 않습니다 — 해당 작업은 브라우저 세션이 필요하며 보안상 의도적으로 제외되었습니다.

## 환경 변수

| 변수 | 기본값 | 설명 |
|----------|---------|-------------|
| `NPG_BASE_URL` | `http://npg-api:8080` | NPG API 기본 URL |
| `NPG_API_TOKEN` | — | NPG API 토큰(`ng_...` 형식). **필수.** NPG 웹 UI 또는 `POST /api/v1/api-tokens`에서 생성. |
| `MCP_PORT` | `8081` | MCP 서버 수신 포트 |
| `MCP_HOST` | `0.0.0.0` | MCP 서버 바인딩 호스트 |
| `MCP_API_TOKEN` | *(비어 있음)* | MCP 엔드포인트에 필요한 Bearer 토큰. **열린(로컬/LAN 전용) 모드로 하려면 비워 두십시오.** `openssl rand -hex 32`로 생성. |
| `MCP_ALLOWED_HOSTS` | `localhost:port` | 엔드포인트가 허용하는 `Host` 헤더의 `host:port`(쉼표 구분, 예: 리버스 프록시 공개 호스트) |
| `MCP_ALLOWED_ORIGINS` | *(비어 있음)* | 교차 출처 요청에서 허용되는 origin(쉼표 구분); CSRF 제한 |
| `MCP_REBINDING_PROTECTION` | `true` | DNS 리바인딩 보호 활성화(프록시가 깨지는 경우에만 비활성화) |
| `MCP_TRANSPORT` | `http` | 전송 모드: 네트워크 배포는 `http`, 직접 파이프는 `stdio`. Docker 이미지 기본값 `http`. |
| `NPG_LOG_LEVEL` | `INFO` | 컨테이너 로그 상세 수준(`DEBUG`/`INFO`/`WARNING`/`ERROR`). `INFO`는 수신 MCP 요청 및 발신 NPG API 호출당 한 줄씩 기록합니다. 아래 "컨테이너 로그" 참고. |
| `NPG_TOOL_LEVEL` | `full` | 계층형 도구 노출: `read`(읽기 전용 129개), `standard`(파괴적 작업 제외 233개), `full`(전체 280개). 읽기 도구는 `npg_get_*`/`npg_list_*`/`npg_view_*`/`npg_download_*`/`npg_check_*`/`npg_detect_*` 이름을 가집니다. 숨겨진 도구는 목록에 표시되지도, 호출도 불가능합니다. 아래 "도구 수준" 참고. |

### 컨테이너 로그

`docker logs npg-mcp -f`로 서버가 받는 요청과 오류를 확인할 수 있습니다. 기본 `INFO` 수준에서 다음이 기록됩니다:

- `MCP request POST /mcp tool=npg_get_proxy_host req=r-1a2b3c4d client=192.168.1.50 -> 200 (12 ms)` — 모든 수신 MCP 요청: HTTP 메서드/경로, JSON-RPC 메서드, 도구 이름, 요청별 상관 ID, 클라이언트 IP, 응답 상태, 소요 시간.
- `NPG GET /api/v1/proxy-hosts/{id} -> 200 (8 ms) req=r-1a2b3c4d` — 모든 발송 NPG API 호출: HTTP 메서드, 엔드포인트 경로, 상태, 소요 시간. `req=` 상관 ID가 위 수신 줄과 일치하므로, 동시 클라이언트가 있어도 어떤 NPG 호출이 어떤 MCP 요청에 속하는지 알 수 있습니다.
- `NPG GET /api/v1/proxy-hosts/{id} -> HTTP 404 (3 ms)` (ERROR 수준) — NPG API 오류(`4xx`/`5xx`). 실패한 호출 경로로 어떤 도구가 실패했는지 특정할 수 있습니다.
- 처리되지 않은 MCP 요청 오류 시 ERROR 수준의 트레이스백.

`req=` ID(`r-<8 hex>` 형식)는 수신 요청마다 새로 생성되며, 해당 요청의 수신 줄과 발신 줄에서 공유되고 로그에만 나타납니다(API 응답이나 도구 결과에는 절대 포함되지 않음). 요청 외부(시작, stdio 모드)의 로그 줄에는 `req=` 필드가 없으므로 기존 로그 파서는 계속 동작합니다.

`NPG_LOG_LEVEL=DEBUG`로 더 상세한 출력을 볼 수 있습니다. **토큰은 절대 기록되지 않습니다** — 기본 수준에서는 요청/응답 본문도 기록되지 않습니다(MCP 도구와 1:1로 대응되는 엔드포인트 경로만 기록). DEBUG는 페이로드가 포함될 수 있는 라이브러리 수준의 세부 정보를 표시하므로 디버깅 시에만 사용하십시오.

### 도구 수준(Toolset Levels)

`NPG_TOOL_LEVEL`은 MCP 클라이언트에 노출되는 도구 수를 제어합니다. 서버 시작 시 한 번 읽으며, 숨겨진 도구는 도구 관리자에서 제거되므로 `tools/list`에 표시되지 않고 호출 시 `Unknown tool` 오류를 반환합니다.

| 수준 | 도구 수 | 범위 |
|-------|-------|-------|
| `read` | 129 | 읽기 전용 도구만 (`npg_get_*`, `npg_list_*`, `npg_view_*`, `npg_download_*`, `npg_check_*`, `npg_detect_*`). NPG 상태를 변경하지 않는 모니터링 에이전트에 적합합니다. |
| `standard` | 230 | 파괴적 작업(모든 삭제/제거, IP 차단, 백업 복원/업로드, 비밀번호/역할/이메일 변경, 토큰 폐기, 정리, 초기화, 세션 종료, 로그 회전)을 제외한 모든 도구. 일상적인 관리 작업에 적합합니다. |
| `full` | 276 | 모든 도구. 기본값이며, 변수를 설정하지 않으면 기존 동작과 동일합니다. |

그 외의 값(또는 미설정)은 `full`로 폴백합니다. `tool-schemas.yaml`은 선택한 수준과 관계없이 항상 전체 276개 도구 참조를 문서화합니다.

## 프로젝트 구조

```
npg_mcp/
  main.py       # 280개의 모든 MCP 도구
  client.py     # API 토큰 인증을 갖춘 HTTP 클라이언트 래퍼
  toolsets.py   # 계층형 도구 노출(NPG_TOOL_LEVEL: read/standard/full)
  __init__.py
Dockerfile      # Multi-stage Docker 빌드
docker-compose.yml
pyproject.toml  # 의존성: mcp>=1.0, httpx>=0.27
tool-schemas.yaml  # 280개 도구의 전체 입력 매개변수 스키마
```

## 라이선스

MIT

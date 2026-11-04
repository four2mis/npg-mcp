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

stdio 모드로 실행 — 패키지는 `.env`를 **자동 로딩하지 않습니다**(`.env`는 Docker Compose의 `env_file:`이 사용). 먼저 환경변수를 export하거나 MCP 클라이언트의 `env` 매핑으로 전달하십시오(아래 로컬 stdio 참고):

```bash
set -a; source .env; set +a
python3 -m npg_mcp.main
```

### Docker 배포(사전 빌드)

GitHub Container Registry에서 이미지 가져오기:

```bash
docker pull ghcr.io/four2mis/npg-mcp:latest
```

릴리스 버전별 태그된 이미지도 제공됩니다(`v` 접두어 없음 — 릴리스는 `1.0.x` 체계):

```bash
docker pull ghcr.io/four2mis/npg-mcp:1.0.0
```

이미지는 **멀티 아키텍처 매니페스트(linux/amd64 + linux/arm64)**로 게시됩니다 — `docker pull`이 플랫폼에 맞는 이미지를 자동으로 선택합니다.

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
    # 모든 런타임 설정은 .env에서 가져옵니다(.env.example 참고). .env.example을 .env로
    # 복사해 값을 채우십시오. 이 파일에 시크릿 없음.
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

그러면 도구가 `mcp__npg_mcp__*`로 나타납니다 — MCP 서버 키 `npg-mcp`는 `npg_mcp`로 정규화됩니다(예: `mcp__npg_mcp__npg_list_proxy_hosts`).

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

### 로컬 stdio(HTTP 서버 없음)

일반 프로세스로 실행하면 서버는 기본값 `MCP_TRANSPORT=stdio`로 동작합니다 — 포트 없음, `MCP_API_TOKEN` 없음. MCP 클라이언트가 프로세스를 직접 실행하고 stdin/stdout으로 통신합니다. command 기반 서버를 지원하는 클라이언트에서 venv 인터프리터를 가리키고, 클라이언트의 `env` 매핑으로 설정을 전달하십시오(패키지는 `.env`를 자동 로딩하지 않음):

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

`MCP_TRANSPORT`는 직접 실행 시 기본값이 stdio이므로 설정할 필요가 없습니다. Hermes도 동일한 stdio 키를 사용합니다:

```yaml
mcp_servers:
  npg-mcp:
    command: /path/to/npg-mcp/.venv/bin/python3
    args: ["-m", "npg_mcp.main"]
    env:
      NPG_BASE_URL: http://<npg-api-host>:8080
      NPG_API_TOKEN: ng_...
```

stdio에서는 `MCP_API_TOKEN`이 적용되지 않습니다 — 접근 제어는 프로세스를 실행할 수 있는 사람이 곧 접근 권한입니다.

### 네트워크 및 방화벽 참고 사항

- 서버는 `MCP_PORT`(기본값 `8081`)에서 수신하며 `MCP_HOST`(기본값 `0.0.0.0`)에 바인딩됩니다.
- **DNS 리바인딩 보호**(기본적으로 `MCP_REBINDING_PROTECTION=true`)는 `MCP_ALLOWED_HOSTS`에 없는 `Host` 헤더의 요청을 거부합니다. 기본값(`localhost:8081,127.0.0.1:8081`)에 포함되지 않은 호스트명/IP로 클라이언트가 접속하는 경우 `.env`의 `MCP_ALLOWED_HOSTS`에 추가하십시오. 예: `MCP_ALLOWED_HOSTS=127.0.0.1:8081,mynas.local:8081,192.168.1.50:8081`.
- **보안 우선:** 신뢰할 수 있는 네트워크에만 MCP 엔드포인트를 노출하십시오. 공개적으로 노출해야 한다면 `MCP_API_TOKEN`을 설정하고 `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS`를 좁게 유지하십시오(README §환경 변수).

## 도구 참조(Tools Reference)

이 서버는 **314개의 MCP 도구**를 29개 카테고리에 걸쳐 노출합니다. 전체 도구 이름, 설명, 입력 매개변수 스키마는 [`tool-schemas.yaml`](tool-schemas.yaml)에 있습니다.

| 카테고리 | 도구 |
|----------|-------|
| **프록시 호스트(Proxy Hosts)** | 47개 |
| **로그(Logs)** | 38개 |
| **보안 및 WAF(Security & WAF)** | 31개 |
| **DNS 제공자(DNS Providers)** | 15개 |
| **인증(Authentication)** | 9개 |
| **인증서(Certificates)** | 15개 |
| **필터 구독(Filter Subscriptions)** | 15개 |
| **클라우드 제공자(Cloud Providers)** | 13개 |
| **URI 차단(URI Block)** | 7개 |
| **설정(Settings)** | 12개 |
| **백업(Backups)** | 8개 |
| **API 토큰(API Tokens)** | 8개 |
| **사용자(Users)** | 9개 |
| **SSO 제공자(SSO Providers)** | 8개 |
| **기타(Other)** | 2개 |
| **대시보드(Dashboard)** | 3개 |
| **트래픽(Traffic)** | 4개 |
| **IP 관리(IP Management)** | 4개 |
| **알림 채널(Notification Channels)** | 7개 |
| **리다이렉트 호스트(Redirect Hosts)** | 6개 |
| **액세스 목록(Access Lists)** | 6개 |
| **지역(Geo)** | 11개 |
| **Fail2ban 및 챌린지(Fail2ban & Challenge)** | 3개 |
| **차단 IP 및 봇(Banned IPs & Bots)** | 7개 |
| **역할(Roles)** | 4개 |
| **시스템(System)** | 18개 |
| **SSL / Nginx** | 2개 |
| **시스템 및 상태(System & Health)** | 1개 |
| **Docker** | 1개 |

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
| `MCP_TRANSPORT` | `stdio` | 전송 모드: 직접 파이프는 `stdio` (직접 실행 기본값), 네트워크 배포는 `http`. Docker 이미지는 `ENV`로 `http`를 설정합니다. |
| `NPG_LOG_LEVEL` | `INFO` | 컨테이너 로그 상세 수준(`DEBUG`/`INFO`/`WARNING`/`ERROR`). `INFO`는 수신 MCP 요청 및 발신 NPG API 호출당 한 줄씩 기록합니다. 아래 "컨테이너 로그" 참고. |
| `NPG_TOOL_LEVEL` | `full` | 계층형 도구 노출: `read`(읽기 전용 141개), `standard`(파괴적 작업 제외 267개), `full`(전체 314개). 읽기 도구는 `npg_get_*`/`npg_list_*`/`npg_view_*`/`npg_download_*`/`npg_check_*`/`npg_detect_*` 이름을 가지며, 쓰기 또는 POST 본문을 사용하는 검사 도구 3개(`npg_check_log_archive`, `npg_detect_telegram_chats`, `npg_check_backup_restore`)는 제외되어 `standard`/`full`에서만 사용할 수 있습니다. 숨겨진 도구는 목록에 표시되지도, 호출도 불가능합니다. 아래 "도구 수준" 참고. |
| `NPG_TOOL_SCOPE_FILTER` | `0` | 선택적 범위 인식 도구 필터링. 활성화하면 서버가 설정된 `NPG_API_TOKEN`의 유효 권한을 **부팅 시 한 번** 확인하여(`GET /api/v1/api-tokens`( `apitoken:read` 필요) + prefix 행 매칭, 실패 시 `GET /api/v1/auth/me` 대체) 해당 스코프가 커버하는 도구만 노출합니다: `NPG_TOOL_LEVEL` ∩ 부여된 스코프. 스코프는 정확한 문자열로 매칭하며(`*` 및 `area:*` 와일드카드 허용) 레거시 스코프를 다른 영역으로 확장하지 않습니다. 스코프 변경은 재시작해야 반영됩니다. 항상 **fail-open**: 두 엔드포인트 모두 실패(403/타임아웃), 토큰 prefix 불일치 또는 중복 일치, 토큰 미설정 시 전체 매니페스트를 유지하며, 권한 주석이 없는 도구는 절대 숨기지 않습니다. 기본값은 꺼짐이며 이때 매니페스트와 도구 수는 변경되지 않습니다. 아래 "범위 필터링" 참고. |
| `NPG_DRY_RUN` | `0` | 드라이런 모드: 참으로 설정(`1`/`true`/`on`)하면 모든 변경 도구가 실제로 실행하는 대신 보낼 요청을 정확히 반환합니다(`{"dry_run": true, "method", "path", "body", ...}`). 아무것도 적용되지 않으므로 실제 인스턴스에 대한 첫 배포를 안전하게 리허설할 수 있습니다. |
| `NPG_HTTP_TIMEOUT` | `30` | 발신 NPG API 요청 타임아웃(초). 대용량 액세스 로그 다운로드, 백업 내보내기/복원, 인증서 업로드, 전체 프록시 호스트 동기화 등 오래 걸리는 엔드포인트에서 `ReadTimeout` 실패를 피하려면 값을 높이세요. `[1, 600]` 범위로 제한되며, 잘못된 값은 경고와 함께 `30`으로 대체됩니다. |
| `NPG_MAX_RESULT_CHARS` | `65536` | 읽기/목록/조회 도구 결과의 직렬화 크기 상한(압축 JSON 문자 수). 초과한 페이로드는 데이터 경계에서만 잘라내고 `truncated` 메타 객체를 덧붙입니다. 호출 시 `expand=true`를 주면 해당 호출만 상한이 해제됩니다. `[1024, 8000000]` 범위로 제한되며, 잘못된 값은 경고와 함께 `65536`으로 대체됩니다. 아래 "결과 봉투와 잘라내기" 참고. |

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
| `read` | 141 | 읽기 전용 도구만 (`npg_get_*`, `npg_list_*`, `npg_view_*`, `npg_download_*`, `npg_check_*`, `npg_detect_*`) — 단, 쓰기 또는 POST 본문을 사용하는 검사 도구 3개(`npg_check_log_archive`, `npg_detect_telegram_chats`, `npg_check_backup_restore`)는 제외되며 `standard`/`full`에만 남습니다. NPG 상태를 변경하지 않는 모니터링 에이전트에 적합합니다. |
| `standard` | 267 | 파괴적 작업(모든 삭제/제거, IP 차단, 백업 복원/업로드, 비밀번호/역할/이메일 변경, 토큰 폐기, 정리, 초기화, 세션 종료, 로그 회전)을 제외한 모든 도구. 일상적인 관리 작업에 적합합니다. |
| `full` | 314 | 모든 도구. 기본값이며, 변수를 설정하지 않으면 기존 동작과 동일합니다. |

그 외의 값(또는 미설정)은 `full`로 폴백합니다. `tool-schemas.yaml`은 선택한 수준과 관계없이 항상 전체 314개 도구 참조를 문서화합니다.

### 범위 필터링(Scope Filtering)

`NPG_TOOL_SCOPE_FILTER`(기본값 `0`, 꺼짐)는 노출 범위를 한 단계 더 좁힙니다. 활성화하면 서버는 설정된 `NPG_API_TOKEN`이 실제로 호출할 수 있는 도구만 노출합니다. MCP 엔드포인트에 범위가 제한된 토큰을 연결할 때 유용합니다 — `read_only` 스코프를 가진 모니터링 토큰에는 어차피 `403`만 받을 쓰기 도구가 필요하지 않습니다.

권한은 **부팅 시 한 번** 다음 두 엔드포인트를 순서대로 확인합니다.

1. `GET /api/v1/api-tokens` — 각 토큰 행에는 표시용 `token_prefix`(`ng_` + 앞 8자)와 `permissions` 배열(`*` 또는 NPG의 레거시 리소스 스코프 15개)이 있습니다. 설정된 토큰이 `token_prefix`로 시작하는 행을 찾습니다.
2. 대체 경로 `GET /api/v1/auth/me` — 권한이 필요 없는 self 라우트입니다. 토큰 호출자에게는 소유자 역할 권한과 토큰 자체 스코프의 교집합인 `effective_permissions`를 반환하며, 이는 NPG가 요청마다 실제로 적용하는 집합입니다. (이 대체 경로가 실무에서 필요합니다: UI에서 만든 토큰은 `*` 또는 레거시 스코프만 가질 수 있고 NPG는 토큰 스코프를 정확한 문자열로 비교하므로, 범위가 제한된 토큰은 항상 `/api/v1/api-tokens`에서 `403`을 받습니다.)

권한 매칭은 NPG의 `APIToken.HasPermission`을 그대로 따릅니다. 도구가 호출하는 모든 라우트의 필요 권한이 `*`, 동일한 문자열, 또는 `area:*` 패밀리 와일드카드로 충족될 때만 노출됩니다. 레거시 스코프가 다른 영역으로 **확장되지 않으며** `write`가 `read`를 함의하지도 않습니다 — 그 확장은 *역할*에 적용되는 규칙입니다(NPG 2.65.4에서 검증: `read_only` 토큰은 proxy/certificate/waf/logs/settings/backup 읽기만 통과하고 redirect/access/authprovider/dnsprovider/ddns/audit/dashboard/user/role에서는 `403`). 노출 집합은 `NPG_TOOL_LEVEL` ∩ `{필요한 모든 권한이 부여된 도구}`입니다.

스냅샷은 부팅 시에만 수행되므로 **NPG UI에서 토큰 스코프를 변경해도 MCP를 재시작해야** 노출 범위가 바뀝니다. 부팅 로그에 확인한 내용이 남고, `npg_get_stack_features`가 동일한 정보를 데이터로 반환합니다(`hidden_by_scope`).

`hidden_by_scope`는 필터가 꺼져 있으면 `null`입니다. `npg_get_stack_features` 자체는 이 필터로 숨겨지지 않으므로, 제한된 서버도 무엇을 숨겼는지 항상 보고할 수 있습니다.

**항상 fail-open입니다.** 동작했을 도구를 숨기는 것이 `403`을 반환하는 도구를 노출하는 것보다 훨씬 나쁩니다 — `npg_create_*` 도구를 숨기면 기능을 존재하게 만드는 유일한 경로가 사라집니다. 따라서 모든 불확실성은 전체 티어 매니페스트를 그대로 유지합니다: 두 조회 엔드포인트 모두 실패(`403`/타임아웃/전송 오류), 토큰 prefix와 일치하는 행 없음, 일치 행이 2개 이상(모호성), `NPG_API_TOKEN` 미설정, 권한 배열이 비었거나 해석 불가. 사유는 `WARNING`으로 기록되고 `hidden_by_scope.reason`으로 반환됩니다. 권한 주석이 없는 도구도 절대 숨기지 않으므로, 새로 연결된 업스트림 엔드포인트가 조용히 사라지지 않습니다.

도구 → 권한 매핑은 `npg_mcp/permission_map.py`에 있으며, NPG 자체의 라우트 권한 레지스트리(`api/internal/middleware/permissions.go`)에서 `scripts/derive_tool_permissions.py`로 생성합니다. 등록된 도구가 맵에 없으면 `tests/test_scopefilter.py`가 실패하므로 맵이 도구 목록보다 뒤처질 수 없습니다. 필터가 꺼져 있으면 매니페스트, 도구 수, 위의 티어 수치는 이 기능이 없을 때와 완전히 동일합니다.

### 도구 애노테이션(Tool Annotations)

모든 도구는 표준 MCP `ToolAnnotations`(`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`)와 사람이 읽을 수 있는 `title`을 함께 제공합니다. 이 값들은 시작 시 각 도구 본문이 호출하는 HTTP 메서드와 도구 수준(toolset level) 뒤에 있는 파괴적 이름 목록에서 계산되므로 코드와 어긋날 수 없으며, 도구 동작 자체는 바꾸지 않습니다:

| 힌트 | `true`인 경우 |
|------|-----------|
| `readOnlyHint` | NPG 호출이 모두 GET인 도구(`npg_get_*`, `npg_list_*`, `npg_download_*` 등). GET 검사 도구 하나는 의도적으로 `false`입니다: `npg_check_backup_restore`는 일회용 백업 행을 만들고 삭제합니다. |
| `destructiveHint` | `standard` 수준에서 숨겨지는 파괴적 도구 집합: 삭제/제거, IP 차단, 초기화, 복원, 토큰 폐기, 자격 증명 변경, 세션 종료, 로그 회전. |
| `idempotentHint` | GET 전용 도구와 멱등 `PUT` 업데이트 — 같은 호출을 반복해도 동일한 최종 상태에 도달합니다. 생성/테스트/삭제는 `false`입니다. |
| `openWorldHint` | 폐쇄형 카탈로그 읽기(국가 목록, 프리셋, 권한 영역, 알려진 봇, WAF 테스트 패턴, 로그 소스/수준, 감사 로그 액션)만 `false`이며, 그 외에는 업스트림·ACME·DNS 공급자·Telegram에 접근하므로 `true`입니다. |

### 결과 봉투와 잘라내기(Result Envelope & Truncation)

모든 도구는 동일한 봉투로 응답합니다: `{"success": true, "data": <payload>}` (도구별 부가 키인 `message`, `encoding`, 페이징 키 등이 함께 올 수 있습니다). 실패 시에는 `{"success": false, "error": "...", "hint": "..."}`를 반환하므로, JSON-RPC `isError` 플래그만 보지 말고 항상 중첩된 `success` 필드를 확인하십시오.

**결과 상한.** 읽기/목록/조회 도구의 단일 결과는 `NPG_MAX_RESULT_CHARS`(기본 `65536`) 문자(압축 JSON 기준)를 초과할 수 없습니다. 초과한 페이로드는 **데이터 경계에서만** 잘라냅니다 — 배열의 꼬리 항목을 버리고, 과도하게 긴 문자열 값은 `... [clamped N chars]` 표식과 함께 줄입니다 — 그리고 `data` 옆에 `truncated` 객체를 추가합니다:

| 필드 | 의미 |
|------|------|
| `total_chars` | 잘라내기 전 결과의 크기(압축 JSON 문자 수) |
| `returned_chars` | 실제로 반환된 결과의 크기(`truncated` 객체 포함) |
| `omitted_items` | 페이로드에서 버려진 배열 꼬리 항목 수 |
| `clamped_strings` | 표식과 함께 줄어든 문자열 값의 개수 |
| `hint` | 나머지를 얻는 방법 — 이 도구가 실제로 가진 더 좁은 매개변수(`limit`/`offset`/`sections`/`lines`) 이름을 알려주며, 없으면 `expand=true`를 안내합니다 |

잘라내기는 구조나 문자열 중간에서 절대 일어나지 않습니다: 축소된 객체에서 봉투를 다시 구성하므로 클라이언트가 받는 JSON은 항상 완전하고 파싱 가능합니다. 상한 이하의 결과는 바이트 단위로 그대로 반환되며 `truncated` 키가 붙지 않습니다.

**예외 경로.** 상한이 적용되는 모든 도구는 `expand: bool = False`를 받습니다. `expand=true`를 주면 해당 호출만 상한이 해제되어 전체 페이로드를 반환합니다 — 잘린 base64 페이로드는 디코딩할 수 없으므로 `npg_download_backup`, `npg_get_certificate_download` 같은 일회성 다운로드에 사용하십시오. `npg_download_log_file`은 일반 상한 대신 자체 256 KB 상한(`truncated: true`, `total_bytes`, `returned_bytes`, `hint` → `npg_view_log_file`)을 유지합니다.

## 프로젝트 구조

```
npg_mcp/
  main.py       # 314개의 모든 MCP 도구
  client.py     # API 토큰 인증을 갖춘 HTTP 클라이언트 래퍼
  toolsets.py   # 도구 수준(NPG_TOOL_LEVEL: read/standard/full) + MCP ToolAnnotations
  resultcap.py  # 공용 결과 상한(NPG_MAX_RESULT_CHARS) + `expand` 예외 경로
  scopefilter.py    # 선택적 범위 인식 필터링(NPG_TOOL_SCOPE_FILTER)
  permission_map.py # 범위 필터용 도구 → NPG 권한 맵(생성 파일)
  __init__.py
Dockerfile      # Multi-stage Docker 빌드
docker-compose.yml
pyproject.toml  # 의존성: mcp>=1.29.0,<2.0.0, httpx>=0.27.0
tool-schemas.yaml  # 314개 도구의 전체 입력 매개변수 스키마
```

## 개발 및 테스트

```bash
pytest tests/ -q   # 오프라인 — NPG API 호출은 모킹(respx)되므로 실제 인스턴스가 필요 없습니다
```

문서(`tool-schemas.yaml`, README 두 언어)는 도구 표면에서 생성되며 동기화가 유지되어야 합니다 — 형식 규약은 [AGENTS.md](AGENTS.md)에 있습니다. 릴리스 기록은 [CHANGELOG.md](CHANGELOG.md).

## 라이선스

MIT

# NPG MCP 서버

[English](README.md) | **한국어**

[NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard)(NPG)용 MCP 서버 — MCP 도구를 통해 프록시 호스트, 인증서, SSL, 보안 규칙, nginx 구성을 관리합니다.

[FastMCP](https://github.com/jlowin/fastmcp)와 [httpx](https://www.python-httpx.org/)로 구축되었습니다.

> **⚠️ AI 에이전트로 바이브 코딩(vibe-coded)되었습니다.** 이 코드베이스는 사람이 직접 작성한 것이 아니라 AI 에이전트가 빠르게 생성한 것입니다. 미세한 결함, 처리되지 않은 엣지 케이스, 버그가 있을 수 있습니다. 실제 운영 중인 NginxProxyGuard 인스턴스에 배포하기 전에 반드시 **격리된(샌드박스) NPG 환경**에서 먼저 테스트하고 코드를 검토하십시오. 이 서버는 실제 프록시 호스트를 생성·수정·삭제·재구성할 수 있으므로, 실제 인프라에 연결하기 전에 반드시 격리된 환경에서 검증하십시오.

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

> **`MCP_API_TOKEN`이 설정된 경우(네트워크에 노출된 모든 배포에서 권장), 모든 MCP 요청은 `Authorization: Bearer *** 헤더를 반드시 포함해야 합니다** — 없으면 `401`이 반환됩니다. 아래 각 클라이언트 설정에서 헤더를 어디에 넣는지 보여줍니다. 토큰(`openssl rand -hex 32`)은 서버의 `.env`에 `MCP_API_TOKEN`으로 설정됩니다.

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
- **헤더:** `Authorization: Bearer <MCP_A...(토큰이 설정된 경우)

Streamable HTTP 서버(`type: "http"` / `sse`)를 지원하는 모든 MCP 클라이언트가 연결할 수 있습니다. 이 엔드포인트는 표준 FastMCP Streamable HTTP 서버입니다.

### 네트워크 및 방화벽 참고 사항

- 서버는 `MCP_PORT`(기본값 `8081`)에서 수신하며 `MCP_HOST`(기본값 `0.0.0.0`)에 바인딩됩니다.
- **DNS 리바인딩 보호**(기본적으로 `MCP_REBINDING_PROTECTION=true`)는 `MCP_ALLOWED_HOSTS`에 없는 `Host` 헤더의 요청을 거부합니다. 기본값(`localhost:8081,127.0.0.1:8081`)에 포함되지 않은 호스트명/IP로 클라이언트가 접속하는 경우 `.env`의 `MCP_ALLOWED_HOSTS`에 추가하십시오. 예: `MCP_ALLOWED_HOSTS=127.0.0.1:8081,mynas.local:8081,192.168.1.50:8081`.
- **보안 우선:** 신뢰할 수 있는 네트워크에만 MCP 엔드포인트를 노출하십시오. 공개적으로 노출해야 한다면 `MCP_API_TOKEN`을 설정하고 `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS`를 좁게 유지하십시오(README §환경 변수).

## 도구 참조(Tools Reference)

이 서버는 **287개의 MCP 도구**를 28개 카테고리로 노출합니다. 각 카테고리는 도구명과 간략한 설명을 표로 제공하며, 전체 입력 매개변수 스키마는 [`tool-schemas.yaml`](tool-schemas.yaml)에 있습니다.

| 카테고리 | 도구 수 |
|----------|---------|
| **프록시 호스트(Proxy Hosts)** | 38개 도구 |
| **로그(Logs)** | 37개 도구 |
| **보안 & WAF(Security & WAF)** | 32개 도구 |
| **DNS 제공자(DNS Providers)** | 15개 도구 |
| **인증(Authentication)** | 15개 도구 |
| **인증서(Certificates)** | 12개 도구 |
| **필터 구독(Filter Subscriptions)** | 12개 도구 |
| **클라우드 제공자(Cloud Providers)** | 11개 도구 |
| **URI 차단(URI Block)** | 10개 도구 |
| **설정(Settings)** | 8개 도구 |
| **백업(Backups)** | 8개 도구 |
| **API 토큰(API Tokens)** | 8개 도구 |
| **사용자(Users)** | 8개 도구 |
| **SSO 제공자(SSO Providers)** | 7개 도구 |
| **기타(Other)** | 6개 도구 |
| **대시보드(Dashboard)** | 6개 도구 |
| **IP 관리(IP Management)** | 6개 도구 |
| **알림 채널(Notification Channels)** | 6개 도구 |
| **리다이렉트 호스트(Redirect Hosts)** | 5개 도구 |
| **액세스 목록(Access Lists)** | 5개 도구 |
| **지역 제한(Geo)** | 5개 도구 |
| **Fail2ban & 챌린지(Fail2ban & Challenge)** | 4개 도구 |
| **차단 IP & 봇(Banned IPs & Bots)** | 4개 도구 |
| **역할(Roles)** | 4개 도구 |
| **시스템(System)** | 4개 도구 |
| **SSL / Nginx** | 3개 도구 |
| **시스템 & 상태(System & Health)** | 2개 도구 |
| **Docker** | 1개 도구 |

### 프록시 호스트(Proxy Hosts) (38)

| 도구 | 설명 |
|------|------|
| `npg_list_proxy_hosts` | 모든 프록시 호스트 목록 |
| `npg_get_proxy_host` | ID로 단일 프록시 호스트 조회 |
| `npg_get_proxy_host_by_domain` | 도메인명으로 프록시 호스트 조회 |
| `npg_create_proxy_host` | 새 역방향 프록시 호스트 생성 |
| `npg_update_proxy_host` | 기존 프록시 호스트 업데이트(부분 업데이트) |
| `npg_delete_proxy_host` | ID로 프록시 호스트 삭제 |
| `npg_test_proxy_host` | 업스트림 연결성 테스트 |
| `npg_sync_proxy_hosts` | 모든 프록시 호스트 구성 동기화 및 nginx 재로드 |
| `npg_clone_proxy_host` | 새 도메인명으로 프록시 호스트 복제 |
| `npg_get_proxy_host_rate_limit` | 속도 제한 구성 GET |
| `npg_update_proxy_host_rate_limit` | 속도 제한 구성 UPDATE |
| `npg_get_proxy_host_bot_filter` | 봇 필터 구성 GET |
| `npg_update_proxy_host_bot_filter` | 봇 필터 구성 UPDATE |
| `npg_delete_proxy_host_bot_filter` | 봇 필터 구성 삭제(글로벌로 폴백) |
| `npg_get_proxy_host_security_headers` | 보안 헤더 구성 GET |
| `npg_update_proxy_host_security_headers` | 보안 헤더 구성 UPDATE |
| `npg_delete_proxy_host_security_headers` | 보안 헤더 구성 삭제(글로벌로 폴백) |
| `npg_get_proxy_host_upstream` | 업스트림/로드 밸런싱 구성 GET |
| `npg_update_proxy_host_upstream` | 업스트림/로드 밸런싱 구성 UPDATE |
| `npg_delete_proxy_host_upstream` | 업스트림 구성 삭제(기본값으로 폴백) |
| `npg_get_proxy_host_uri_block` | URI 차단 구성 GET |
| `npg_update_proxy_host_uri_block` | URI 차단 구성 UPDATE |
| `npg_delete_proxy_host_uri_block` | URI 차단 구성 삭제(글로벌로 폴백) |
| `npg_add_proxy_host_uri_block_rule` | 단일 URI 차단 규칙 추가 |
| `npg_delete_proxy_host_uri_block_rule` | 단일 URI 차단 규칙 제거 |
| `npg_get_proxy_host_geo` | 지역 제한 구성 GET |
| `npg_create_proxy_host_geo` | 지역 제한 CREATE |
| `npg_update_proxy_host_geo` | 지역 제한 UPDATE |
| `npg_delete_proxy_host_geo` | 지역 제한 DELETE |
| `npg_get_proxy_host_fail2ban` | fail2ban 구성 GET |
| `npg_update_proxy_host_fail2ban` | fail2ban 구성 UPDATE |
| `npg_delete_proxy_host_fail2ban` | fail2ban 구성 삭제(글로벌로 폴백) |
| `npg_get_proxy_host_challenge` | CAPTCHA/챌린지 구성 GET |
| `npg_update_proxy_host_challenge` | CAPTCHA/챌린지 구성 UPDATE |
| `npg_delete_proxy_host_challenge` | CAPTCHA/챌린지 구성 DELETE |
| `npg_set_proxy_host_favorite` | 프록시 호스트를 즐겨찾기로 토글 |
| `npg_get_proxy_host_cloud_blocking` | 호스트별 클라우드 제공자 차단 GET |
| `npg_update_proxy_host_cloud_blocking` | 호스트별 클라우드 제공자 차단 UPDATE |
| `npg_regenerate_config` | 특정 프록시 호스트용 nginx 구성 재생성 |

### 로그(Logs) (37)

| 도구 | 설명 |
|------|------|
| `npg_get_logs` | 액세스 로그 조회 |
| `npg_get_log_settings` | 로그 설정 조회 |
| `npg_update_log_settings` | 로그 설정 업데이트 |
| `npg_get_log_stats` | 로그 통계 조회 |
| `npg_list_audit_logs` | 감사 로그 항목 목록 |
| `npg_list_system_logs` | 시스템 로그 목록 |
| `npg_list_log_files` | 모든 로그 파일 목록 |
| `npg_download_log_file` | 파일명으로 로그 파일 다운로드 |
| `npg_view_log_file` | 로그 파일 내용 조회 |
| `npg_rotate_log_file` | 파일명으로 로그 파일 회전 |
| `npg_delete_log_file` | 파일명으로 로그 파일 삭제 |
| `npg_get_catalog` | 악성 규칙 카탈로그 조회 |
| `npg_subscribe_catalog` | 카탈로그 항목 구독 |
| `npg_get_filter_subscription_catalog` | 커리커드 필터 카탈로그 조회 |
| `npg_subscribe_filter_catalog` | 하나 이상의 필터 목록 구독 |
| `npg_get_certificate_logs` | 인증서의 발급 로그 스트림 조회 |
| `npg_post_log` | 로그 항목 수동 삽입 |
| `npg_cleanup_logs` | 보존 기간 초과 nginx 액세스 로그 삭제 |
| `npg_get_log_autocomplete_hosts` | 액세스 로그에서 고유 호스트 목록 |
| `npg_get_log_autocomplete_ips` | 액세스 로그에서 고유 클라이언트 IP 목록 |
| `npg_get_log_autocomplete_user_agents` | 액세스 로그에서 고유 User-Agent 목록 |
| `npg_get_log_autocomplete_uris` | 액세스 로그에서 고유 요청 URI 목록 |
| `npg_get_log_autocomplete_countries` | 액세스 로그에서 고유 국가 목록 |
| `npg_get_log_autocomplete_methods` | 액세스 로그에서 고유 HTTP 메서드 목록 |
| `npg_get_log_filter_presets` | 저장된 로그 필터 프리셋 목록 |
| `npg_create_log_filter_preset` | 로그 필터 프리셋 저장 |
| `npg_update_log_filter_preset` | 로그 필터 프리셋 업데이트 |
| `npg_delete_log_filter_preset` | 로그 필터 프리셋 삭제 |
| `npg_cleanup_system_logs` | 보존 기간 초과 시스템 로그 삭제 |
| `npg_get_system_log_sources` | 선택 가능한 시스템 로그 소스 조회 |
| `npg_get_system_log_levels` | 선택 가능한 시스템 로그 레벨 조회 |
| `npg_get_system_log_stats` | 시스템 로그 통계 조회 |
| `npg_get_system_settings_logs` | 컨테이너 로그 수집기 구성 조회 |
| `npg_update_system_settings_logs` | 컨테이너 로그 수집기 구성 업데이트 |
| `npg_get_audit_log_actions` | 감사 로그의 액션 값 목록 |
| `npg_get_audit_log_resource_types` | 감사 로그의 리소스 유형 목록 |
| `npg_get_audit_log_api_tokens` | 모든 토큰의 최근 API 토큰 사용량 목록 |

### 보안 & WAF(Security & WAF) (32)

| 도구 | 설명 |
|------|------|
| `npg_apply_security_header_preset` | 보안 헤더 프리셋 적용(엄격/균형/완화) |
| `npg_get_security_headers_presets` | 사용 가능한 보안 헤더 프리셋 조회 |
| `npg_list_exploit_rules` | 악성 규칙 목록 |
| `npg_get_exploit_rule` | ID로 악성 규칙 조회 |
| `npg_create_exploit_rule` | 악성 규칙 생성 |
| `npg_update_exploit_rule` | 악성 규칙 업데이트 |
| `npg_delete_exploit_rule` | 악성 규칙 삭제 |
| `npg_toggle_exploit_rule` | 악성 규칙 상태 토글 |
| `npg_list_waf_rules` | 모든 WAF 규칙 목록 |
| `npg_get_waf_hosts` | 모든 프록시 호스트의 WAF 구성 조회 |
| `npg_get_waf_host_config` | 특정 프록시 호스트의 WAF 구성 조회 |
| `npg_disable_waf_rule` | 특정 프록시 호스트의 WAF 규칙 비활성화 |
| `npg_get_global_security_headers` | 글로벌 보안 헤더 구성 GET |
| `npg_update_global_security_headers` | 글로벌 보안 헤더 구성 UPDATE |
| `npg_get_global_waf` | 글로벌 WAF 구성 GET |
| `npg_update_global_waf` | 글로벌 WAF 구성 UPDATE |
| `npg_get_exploit_rules_hosts` | 악성 차단을 활성화한 프록시 호스트 목록 |
| `npg_get_exploit_rules_for_host` | 호스트의 제외 상태로 악성 규칙 목록 |
| `npg_exclude_exploit_rule_from_host` | 단일 프록시 호스트에서 악성 규칙 제외 |
| `npg_remove_exploit_rule_exclusion_from_host` | 호스트 제외 제거(해당 호스트에서 규칙 재활성화) |
| `npg_global_exclude_exploit_rule` | 모든 호스트에서 악성 규칙 제외 |
| `npg_remove_exploit_rule_global_exclusion` | 글로벌 제외 제거(모든 곳에서 규칙 재활성화) |
| `npg_get_waf_global_rules` | 글로벌 제외 상태로 모든 OWASP CRS 규칙 목록 |
| `npg_get_waf_global_exclusions` | 글로벌 비활성화된 CRS 규칙 목록 |
| `npg_get_waf_global_history` | 글로벌 WAF 정책 변경 이력 조회 |
| `npg_disable_waf_global_rule` | CRS 규칙을 글로벌로 비활성화 |
| `npg_enable_waf_global_rule` | CRS 규칙을 글로벌로 재활성화 |
| `npg_get_waf_host_history` | 프록시 호스트의 WAF 정책 변경 이력 조회 |
| `npg_disable_waf_rule_by_host` | 도메인을 소유한 호스트의 CRS 규칙 비활성화 |
| `npg_get_waf_test_patterns` | 내장 WAF 공격 테스트 패턴 목록 |
| `npg_test_waf_pattern` | 대상 URL에 공격 페이로드 하나 발송 |
| `npg_test_waf_all_patterns` | 대상 URL에 모든 공격 페이로드 발송 |

### DNS 제공자(DNS Providers) (15)

| 도구 | 설명 |
|------|------|
| `npg_list_dns_providers` | DNS-01 챌린지용 DNS 제공자 목록 |
| `npg_get_dns_provider` | ID로 DNS 제공자 조회 |
| `npg_create_dns_provider` | DNS-01 챌린지용 DNS 제공자 생성 |
| `npg_update_dns_provider` | DNS 제공자 업데이트 |
| `npg_delete_dns_provider` | DNS 제공자 삭제 |
| `npg_test_dns_provider` | DNS 제공자 자격 증명 테스트 |
| `npg_list_ddns_records` | 모든 DDNS 기록 목록 |
| `npg_create_ddns_record` | DDNS 기록 생성 |
| `npg_get_ddns_record` | ID로 DDNS 기록 조회 |
| `npg_update_ddns_record` | DDNS 기록 업데이트 |
| `npg_delete_ddns_record` | DDNS 기록 삭제 |
| `npg_sync_ddns_records` | 모든 활성화된 DDNS 기록 동기화 |
| `npg_sync_ddns_record` | 단일 DDNS 기록 동기화 |
| `npg_import_ddns_from_hosts` | DDNS 활성화 프록시 호스트에서 DDNS 기록 가져오기 |
| `npg_get_dns_provider_default` | 인증서 발급용 기본 DNS 제공자 조회 |

### 인증(Authentication) (15)

| 도구 | 설명 |
|------|------|
| `npg_get_auth_status` | 인증 상태 GET |
| `npg_get_auth_account` | 내 계정 정보 GET |
| `npg_auth_change_credentials` | 내 사용자명과 비밀번호 변경(초기 설정) |
| `npg_auth_2fa_setup` | 2FA 등록 시작(QR 코드 반환) |
| `npg_auth_2fa_enable` | 2FA 활성화 |
| `npg_auth_2fa_disable` | 2FA 비활성화 |
| `npg_get_auth_language` | 인증된 사용자의 UI 언어 선호도 GET |
| `npg_update_auth_language` | 인증된 사용자의 UI 언어 SET |
| `npg_get_auth_font` | 인증된 사용자의 UI 폰트 패밀리 선호도 GET |
| `npg_update_auth_font` | 인증된 사용자의 UI 폰트 패밀리 SET |
| `npg_list_auth_providers` | ForwardAuth 제공자(Authelia, Authentik, 커스텀) 목록 |
| `npg_create_auth_provider` | ForwardAuth 제공자 생성 |
| `npg_get_auth_provider` | ID로 ForwardAuth 제공자 조회 |
| `npg_update_auth_provider` | ForwardAuth 제공자 업데이트 |
| `npg_delete_auth_provider` | ForwardAuth 제공자 삭제 |

### 인증서(Certificates) (12)

| 도구 | 설명 |
|------|------|
| `npg_list_certificates` | 모든 SSL/TLS 인증서 목록 |
| `npg_get_certificate` | ID로 인증서 조회 |
| `npg_create_certificate` | 새 Let's Encrypt 인증서 요청 |
| `npg_delete_certificate` | ID로 인증서 삭제 |
| `npg_renew_certificate` | ID로 인증서 갱신 |
| `npg_get_expiring_certificates` | 만료 임박 인증서 조회 |
| `npg_get_certificate_history` | 인증서 이력 조회 |
| `npg_upload_certificate` | 인증서 파일 업로드 |
| `npg_delete_certificate_errors` | 오류 상태의 모든 인증서 일괄 삭제 |
| `npg_clear_certificate_error` | 인증서의 오류 상태 지우기 |
| `npg_upload_certificate_pem` | 커스텀 인증서의 PEM 자료 교체 |
| `npg_get_certificate_download` | 인증서 자료(PEM) 다운로드 |

### 필터 구독(Filter Subscriptions) (12)

| 도구 | 설명 |
|------|------|
| `npg_list_filter_subscriptions` | 모든 필터 구독 목록 |
| `npg_create_filter_subscription` | 필터 목록 URL 구독 |
| `npg_get_filter_subscription` | 항목과 제외가 포함된 필터 구독 조회 |
| `npg_update_filter_subscription` | 필터 구독 업데이트 |
| `npg_delete_filter_subscription` | 필터 구독 삭제 |
| `npg_refresh_filter_subscription` | 필터 구독 항목 새로 고침 |
| `npg_get_filter_subscription_exclusions` | 필터 구독의 호스트 제외 목록 |
| `npg_add_filter_subscription_exclusion` | 호스트를 필터 구독에서 제외 |
| `npg_remove_filter_subscription_exclusion` | 호스트 제외 제거 |
| `npg_get_filter_subscription_entry_exclusions` | 필터 구독의 항목 제외 목록 |
| `npg_add_filter_subscription_entry_exclusion` | 단일 항목 값을 필터 구독에서 제외 |
| `npg_remove_filter_subscription_entry_exclusion` | 항목 제외 제거 |

### 클라우드 제공자(Cloud Providers) (11)

| 도구 | 설명 |
|------|------|
| `npg_list_cloud_providers` | 클라우드 제공자 목록(인증서 DNS 챌린지) |
| `npg_get_cloud_provider` | 슬러그로 클라우드 제공자 조회 |
| `npg_create_cloud_provider` | 클라우드 제공자 생성(IP 범위 데이터베이스 항목) |
| `npg_update_cloud_provider` | 슬러그로 클라우드 제공자 업데이트 |
| `npg_delete_cloud_provider` | 슬러그로 클라우드 제공자 삭제 |
| `npg_list_cloud_providers_by_region` | 지역별 클라우드 제공자 목록 |
| `npg_get_cloudflare_tunnel` | Cloudflare Tunnel 구성 조회 |
| `npg_update_cloudflare_tunnel` | Cloudflare Tunnel 구성 업데이트 |
| `npg_get_cloudflare_tunnel_status` | Cloudflare Tunnel 상태 조회 |
| `npg_get_global_cloud_providers` | 글로벌 클라우드 제공자 구성 GET |
| `npg_update_global_cloud_providers` | 글로벌 클라우드 제공자 구성 UPDATE |

### URI 차단(URI Block) (10)

| 도구 | 설명 |
|------|------|
| `npg_list_uri_blocks` | 모든 URI 블록(글로벌 및 호스트별) 목록 |
| `npg_create_uri_block` | 프록시 호스트용 URI 블록 생성 |
| `npg_get_uri_block` | ID로 URI 블록 조회 |
| `npg_update_uri_block` | URI 블록 업데이트 |
| `npg_delete_uri_block` | ID로 URI 블록 삭제 |
| `npg_bulk_add_uri_block_rule` | URI 규칙 일괄 추가 |
| `npg_get_global_uri_block` | 글로벌 URI 블록 구성 GET |
| `npg_update_global_uri_block` | 글로벌 URI 블록 구성 UPDATE |
| `npg_add_global_uri_block_rule` | 글로벌 URI 블록에 규칙 추가 |
| `npg_delete_global_uri_block_rule` | 글로벌 URI 블록에서 규칙 삭제 |

### 설정(Settings) (8)

| 도구 | 설명 |
|------|------|
| `npg_get_settings` | 글로벌 NPG 설정 조회 |
| `npg_update_settings` | 글로벌 NPG 설정 업데이트 |
| `npg_get_system_settings` | 시스템 설정(서버명, 시간대, 로케일) 조회 |
| `npg_update_system_settings` | 시스템 설정 업데이트 |
| `npg_get_public_ui_settings` | 공개 UI 설정(인증 불필요) 조회 |
| `npg_reset_settings` | 글로벌 nginx 설정을 기본값으로 초기화 |
| `npg_get_settings_presets` | 사용 가능한 글로벌 설정 프리셋 목록 |
| `npg_apply_settings_preset` | 글로벌 설정 프리셋 적용 |

### 백업(Backups) (8)

| 도구 | 설명 |
|------|------|
| `npg_list_backups` | 모든 백업 목록 |
| `npg_get_backup` | ID로 백업 조회 |
| `npg_create_backup` | 새 백업 생성 |
| `npg_delete_backup` | ID로 백업 삭제 |
| `npg_restore_backup` | 백업에서 복원 |
| `npg_download_backup` | ID로 백업 다운로드 |
| `npg_upload_restore_backup` | 백업 파일 업로드 및 복원 |
| `npg_get_backup_stats` | 백업 통계 조회 |

### API 토큰(API Tokens) (8)

| 도구 | 설명 |
|------|------|
| `npg_list_api_tokens` | 모든 API 토큰 목록 |
| `npg_get_api_token` | ID로 API 토큰 조회 |
| `npg_create_api_token` | 새 API 토큰 생성 |
| `npg_update_api_token` | API 토큰 업데이트 |
| `npg_revoke_api_token` | ID로 API 토큰 무효화 |
| `npg_delete_api_token` | ID로 API 토큰 삭제 |
| `npg_get_api_token_permissions` | API 토큰이 가질 수 있는 권한 문자열 목록 |
| `npg_get_api_token_usage` | API 토큰의 최근 사용량 조회 |

### 사용자(Users) (8)

| 도구 | 설명 |
|------|------|
| `npg_list_users` | 모든 사용자 목록 |
| `npg_get_user` | ID로 사용자 조회 |
| `npg_create_user` | 새 사용자 생성 |
| `npg_set_user_password` | 사용자 비밀번호 설정/재설정 |
| `npg_assign_user_role` | 사용자에게 역할 할당 |
| `npg_end_user_sessions` | 사용자의 모든 세션 종료(강제 로그아웃) |
| `npg_delete_user` | ID로 사용자 삭제 |
| `npg_auth_change_username` | 내 사용자명 변경 |

### SSO 제공자(SSO Providers) (7)

| 도구 | 설명 |
|------|------|
| `npg_list_sso_providers` | 모든 SSO 제공자 목록 |
| `npg_create_sso_provider` | 새 SSO 제공자 생성 |
| `npg_update_sso_provider` | SSO 제공자 업데이트 |
| `npg_delete_sso_provider` | SSO 제공자 삭제 |
| `npg_test_sso_provider` | SSO 제공자 구성 테스트(테스트 로그인 흐름) |
| `npg_get_auth_sso_providers` | 로그인 화면에 표시된 SSO 제공자 목록 |
| `npg_auth_sso_start` | SSO 로그인 흐름 시작 |

### 기타(Other) (6)

| 도구 | 설명 |
|------|------|
| `npg_list_countries` | GeoIP 차단을 위한 사용 가능한 국가 코드 목록 |
| `npg_detect_telegram_chats` | 알림용 사용 가능한 Telegram 채팅 감지 |
| `npg_import_from_hosts` | 기존 호스트에서 인증서 가져오기 |
| `npg_test_acme` | DNS 제공자용 ACME 구성 테스트 |
| `npg_get_global_rate_limit` | 글로벌 속도 제한 구성 GET |
| `npg_update_global_rate_limit` | 글로벌 속도 제한 구성 UPDATE |

### 대시보드(Dashboard) (6)

| 도구 | 설명 |
|------|------|
| `npg_get_dashboard` | 대시보드 데이터 조회(프록시 호스트, 인증서 요약 등) |
| `npg_get_dashboard_health` | 시스템 상태 조회 |
| `npg_get_dashboard_geoip_stats` | 국가별 GeoIP 통계 GET |
| `npg_get_dashboard_containers` | Docker 컨테이너 통계 조회 |
| `npg_get_dashboard_stats` | 시간별 통계 조회 |
| `npg_get_dashboard_health_history` | 시스템 상태 이력 조회 |

### IP 관리(IP Management) (6)

| 도구 | 설명 |
|------|------|
| `npg_ban_ip` | IP 주소 차단 |
| `npg_unban_ip` | ID로 IP 차단 해제 |
| `npg_bulk_unban_ips` | 여러 차단 IP 기록 일괄 차단 해제 |
| `npg_get_ban_history` | 차단/차단 해제 이벤트 이력 조회 |
| `npg_get_ban_history_stats` | 차단/차단 해제 이력 통계 조회 |
| `npg_get_ban_history_for_ip` | 특정 IP의 차단 이력 조회 |

### 알림 채널(Notification Channels) (6)

| 도구 | 설명 |
|------|------|
| `npg_list_notification_channels` | 모든 알림 채널 목록 |
| `npg_create_notification_channel` | 알림 채널 생성 |
| `npg_update_notification_channel` | 알림 채널 업데이트 |
| `npg_delete_notification_channel` | 알림 채널 삭제 |
| `npg_test_notification_channel` | 알림 채널 테스트(테스트 메시지 발송) |
| `npg_get_notification_deliveries` | 알림 채널의 배달 이력 조회 |

### 리다이렉트 호스트(Redirect Hosts) (5)

| 도구 | 설명 |
|------|------|
| `npg_list_redirect_hosts` | 모든 리다이렉트 호스트 목록 |
| `npg_get_redirect_host` | ID로 리다이렉트 호스트 조회 |
| `npg_create_redirect_host` | 새 리다이렉트 호스트 생성 |
| `npg_update_redirect_host` | 리다이렉트 호스트 업데이트 |
| `npg_delete_redirect_host` | ID로 리다이렉트 호스트 삭제 |

### 액세스 목록(Access Lists) (5)

| 도구 | 설명 |
|------|------|
| `npg_list_access_lists` | 모든 액세스 목록(인증/제한 목록) |
| `npg_get_access_list` | ID로 액세스 목록 조회 |
| `npg_create_access_list` | 새 액세스 목록 생성 |
| `npg_update_access_list` | 액세스 목록 업데이트 |
| `npg_delete_access_list` | ID로 액세스 목록 삭제 |

### 지역 제한(Geo) (5)

| 도구 | 설명 |
|------|------|
| `npg_get_geoip_status` | GeoIP 데이터베이스 업데이트 상태 조회 |
| `npg_update_geoip` | GeoIP 데이터베이스 업데이트 |
| `npg_get_global_geo` | 글로벌 GeoIP 제한 구성 GET |
| `npg_update_global_geo` | 글로벌 GeoIP 제한 구성 UPDATE |
| `npg_get_geoip_history` | GeoIP 데이터베이스 업데이트 실행 이력 조회 |

### Fail2ban & 챌린지(Fail2ban & Challenge) (4)

| 도구 | 설명 |
|------|------|
| `npg_verify_challenge` | CAPTCHA 솔루션 검증(공개 엔드포인트) |
| `npg_get_challenge_config` | 글로벌 CAPTCHA 챌린지 구성 GET |
| `npg_update_challenge_config` | 글로벌 CAPTCHA 챌린지 구성 UPDATE |
| `npg_get_challenge_stats` | CAPTCHA 챌린지 통계 GET |

### 차단 IP & 봇(Banned IPs & Bots) (4)

| 도구 | 설명 |
|------|------|
| `npg_list_banned_ips` | 차단된 IP 주소 목록 |
| `npg_get_bots_known` | 알려진 봇 User-Agent 시그니처 목록 |
| `npg_get_global_bot_filter` | 글로벌 봇 필터 구성 GET |
| `npg_update_global_bot_filter` | 글로벌 봇 필터 구성 UPDATE |

### 역할(Roles) (4)

| 도구 | 설명 |
|------|------|
| `npg_list_roles` | 모든 역할 목록 |
| `npg_create_role` | 새 역할 생성 |
| `npg_update_role` | 역할 업데이트 |
| `npg_delete_role` | ID로 역할 삭제 |

### 시스템(System) (4)

| 도구 | 설명 |
|------|------|
| `npg_check_update` | 사용 가능한 NPG 업데이트 확인 |
| `npg_get_status` | 구성 요소 상태 — 모든 NPG 서브시스템의 상태 |
| `npg_check_npg_update` | 최신 NPG 릴리스 버전 확인 |
| `npg_get_global_rate_limit` | 글로벌 속도 제한 구성 GET |

### SSL / Nginx (3)

| 도구 | 설명 |
|------|------|
| `npg_reload_nginx` | 전체 재시작 없이 nginx 구성 재로드 |
| `npg_sync_nginx` | 모든 구성 동기화 및 nginx 재로드 |
| `npg_test_nginx` | nginx 구성 유효성 테스트 |

### 시스템 & 상태(System & Health) (2)

| 도구 | 설명 |
|------|------|
| `npg_get_upstream_health` | 업스트림 풀의 상태 GET |
| `npg_get_health_detailed` | 상세 상태 스냅샷 조회 |

### Docker (1)

| 도구 | 설명 |
|------|------|
| `npg_get_docker_containers` | Docker 컨테이너 통계 조회 |

## 인증

서버는 `NPG_USERNAME`과 `NPG_PASSWORD`를 사용해 **첫 사용 시 자동 인증**합니다. 수동 토큰 관리가 필요 없습니다 — 모든 도구 호출이 인증을 자동으로 갱신합니다.

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
  main.py       # 287개의 모든 MCP 도구
  client.py     # 자동 인증을 갖춘 HTTP 클라이언트 래퍼
  __init__.py
Dockerfile      # Multi-stage Docker 빌드
docker-compose.yml
pyproject.toml  # 의존성: mcp>=1.0, httpx>=0.27
tool-schemas.yaml  # 287개 도구의 전체 입력 매개변수 스키마
```

## 라이선스

MIT

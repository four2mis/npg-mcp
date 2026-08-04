# NPG MCP 서버

[English](README.md) | **한국어**

[NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard)(NPG)용 MCP 서버 — MCP 도구를 통해 프록시 호스트, 인증서, SSL, 보안 규칙, nginx 구성을 관리합니다.

[FastMCP](https://github.com/jlowin/fastmcp)와 [httpx](https://www.python-httpx.org/)로 구축되었습니다.

> **⚠️ AI 에이전트로 바이브 코딩(vibe-coded)되었습니다.** 이 코드베이스는 사람이 직접 작성한 것이 아니라 AI 에이전트가 빠르게 생성한 것입니다. 미세한 결함, 처리되지 않은 엣지 케이스, 버그가 있을 수 있습니다. 실제 운영 중인 NginxProxyGuard 인스턴스에 배포하기 전에 반드시 **격리된(샌드박스) NPG 환경**에서 먼저 테스트하고 코드를 검토하십시오. 이 서버는 실제 프록시 호스트를 생성·수정·삭제·재구성할 수 있으므로, 실제 인프라에 연결하기 전에 반드시 격리된 환경에서 검증하십시오.

## 도구 참조(Tools Reference)

이 서버는 **105개의 MCP 도구**를 노출합니다. 각 도구는 간단한 설명과 **입력 매개변수 스키마**(매개변수, 유형, 필수 여부, 기본값)와 함께 아래에 문서화되어 있습니다. 도구는 다음 카테고리로 그룹화됩니다:

- **인증(Auth)** — 1개 도구
- **대시보드(Dashboard)** — 3개 도구
- **프록시 호스트(Proxy Hosts)** — 10개 도구
- **SSL / Nginx** — 8개 도구
- **리다이렉트 호스트(Redirect Hosts)** — 5개 도구
- **보안(호스트별)** — 12개 도구
- **지역 제한(Geo Restriction)** — 5개 도구
- **Fail2ban & 챌린지** — 6개 도구
- **액세스 목록(Access Lists)** — 5개 도구
- **DNS 제공자(DNS Providers)** — 6개 도구
- **클라우드 제공자(Cloud Providers)** — 5개 도구
- **GeoIP** — 2개 도구
- **차단 IP & 봇(Banned IPs & Bots)** — 4개 도구
- **URI 차단(URI Block)** — 2개 도구
- **WAF & 악성 규칙(WAF & Exploit Rules)** — 10개 도구
- **설정(Settings)** — 4개 도구
- **로그(Logs)** — 6개 도구
- **백업(Backups)** — 5개 도구
- **API 토큰(API Tokens)** — 6개 도구

### 인증(Auth) (1)

#### `npg_change_password`

Change the current user's password. REQUIRED: current_password, new_password (min 8 chars).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `current_password` | `str` | ✔ |  |
| `new_password` | `str` | ✔ |  |

### 대시보드(Dashboard) (3)

#### `npg_get_dashboard`

Get dashboard data (summary of proxy hosts, certificates, etc.).

_매개변수 없음._

#### `npg_get_dashboard_health`

Get system health status.

_매개변수 없음._

#### `npg_get_dashboard_geoip_stats`

GET GeoIP statistics by country for the dashboard.

_매개변수 없음._

### 프록시 호스트(Proxy Hosts) (10)

#### `npg_list_proxy_hosts`

List all proxy hosts. Returns a list of proxy host objects.

_매개변수 없음._

#### `npg_get_proxy_host`

Get a single proxy host by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_get_proxy_host_by_domain`

Get a proxy host by its domain name.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `domain` | `str` | ✔ |  |

#### `npg_create_proxy_host`

Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: forward_scheme, block_normal, waf_enabled, block_http, ssl_forced, ssl_cert_id, cache_enabled, etc.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `domain_names` | `array<str>` | ✔ |  |
| `forward_host` | `str` | ✔ |  |
| `forward_port` | `int` | ✔ |  |
| `forward_scheme` | `str` | — | `"http"` |
| `block_normal` | `bool` | — | `false` |
| `waf_enabled` | `bool` | — | `false` |
| `block_http` | `bool` | — | `false` |
| `ssl_enabled` | `bool` | — | `true` |
| `ssl_forced` | `bool` | — | `true` |
| `ssl_cert_id` | `str/int/null` | — | `null` |
| `cache_enabled` | `bool` | — | `false` |
| `cache_template` | `str` | — | `"ignore"` |
| `advanced_config` | `str` | — | `""` |
| `enable_proxy_headers` | `bool` | — | `true` |
| `host_header` | `str/null` | — | `null` |
| `extra_domains` | `array<any>/null` | — | `null` |
| `block_exploits` | `bool` | — | `false` |

#### `npg_update_proxy_host`

Update an existing proxy host. Pass only the fields you want to change. Use `?skip_nginx=true` to skip nginx regeneration.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `domain_names` | `array<any>/null` | — | `null` |
| `forward_host` | `str/null` | — | `null` |
| `forward_port` | `int/null` | — | `null` |
| `forward_scheme` | `str/null` | — | `null` |
| `block_normal` | `bool/null` | — | `null` |
| `waf_enabled` | `bool/null` | — | `null` |
| `block_http` | `bool/null` | — | `null` |
| `ssl_forced` | `bool/null` | — | `null` |
| `ssl_cert_id` | `str/int/null` | — | `null` |
| `cache_enabled` | `bool/null` | — | `null` |
| `cache_template` | `str/null` | — | `null` |
| `advanced_config` | `str/null` | — | `null` |
| `enable_proxy_headers` | `bool/null` | — | `null` |
| `host_header` | `str/null` | — | `null` |
| `extra_domains` | `array<any>/null` | — | `null` |
| `enabled` | `bool/null` | — | `null` |
| `ssl_http2` | `bool/null` | — | `null` |
| `ssl_http3` | `bool/null` | — | `null` |
| `block_exploits` | `bool/null` | — | `null` |
| `skip_nginx` | `bool` | — | `false` |

#### `npg_delete_proxy_host`

Delete a proxy host by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_test_proxy_host`

Test upstream connectivity for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_regenerate_config`

Regenerate nginx config for a specific proxy host without touching others.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_sync_proxy_hosts`

Sync all proxy host configs and reload nginx.

_매개변수 없음._

#### `npg_clone_proxy_host`

Clone a proxy host with new domain names. Returns the new proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `domain_names` | `array<str>` | ✔ |  |

### SSL / Nginx (8)

#### `npg_list_certificates`

List all SSL/TLS certificates.

_매개변수 없음._

#### `npg_get_certificate`

Get a certificate by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `cert_id` | `str/int` | ✔ |  |

#### `npg_create_certificate`

Request a new Let's Encrypt certificate. Required: domain_names (array), email. Optional: provider (e.g. 'letsencrypt'), dns_provider_id, etc.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `domain_names` | `array<str>` | ✔ |  |
| `email` | `str` | ✔ |  |
| `provider` | `str` | — | `"letsencrypt"` |
| `dns_provider_id` | `str/null` | — | `null` |

#### `npg_delete_certificate`

Delete a certificate by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `cert_id` | `str/int` | ✔ |  |

#### `npg_renew_certificate`

Renew a certificate by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `cert_id` | `str/int` | ✔ |  |

#### `npg_reload_nginx`

Reload nginx configuration without full restart.

_매개변수 없음._

#### `npg_sync_nginx`

Sync all configs and reload nginx.

_매개변수 없음._

#### `npg_test_nginx`

Test nginx configuration for validity.

_매개변수 없음._

### 리다이렉트 호스트(Redirect Hosts) (5)

#### `npg_list_redirect_hosts`

List all redirect hosts.

_매개변수 없음._

#### `npg_get_redirect_host`

Get a redirect host by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_create_redirect_host`

Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, default 301).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `domain_names` | `array<str>` | ✔ |  |
| `forward_domain_name` | `str` | ✔ |  |
| `forward_scheme` | `str` | — | `"auto"` |
| `preserve_path` | `bool` | — | `true` |
| `redirect_code` | `int` | — | `301` |

#### `npg_update_redirect_host`

Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `domain_names` | `array<any>/null` | — | `null` |
| `forward_domain_name` | `str/null` | — | `null` |
| `forward_scheme` | `str/null` | — | `null` |
| `preserve_path` | `bool/null` | — | `null` |
| `redirect_code` | `int/null` | — | `null` |

#### `npg_delete_redirect_host`

Delete a redirect host by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

### 보안(호스트별) (12)

#### `npg_get_proxy_host_rate_limit`

GET rate limit configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_update_proxy_host_rate_limit`

UPDATE rate limit configuration for a proxy host. Body: enabled, requests_per_second, burst_size, zone_size, limit_by (ip/uri/ip_uri), limit_response

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `requests_per_second` | `int` | ✔ |  |
| `burst_size` | `int` | ✔ |  |
| `zone_size` | `str` | — | `"10m"` |
| `limit_by` | `str` | — | `"ip"` |
| `limit_response` | `int` | — | `429` |

#### `npg_get_proxy_host_bot_filter`

GET bot filter configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_update_proxy_host_bot_filter`

UPDATE bot filter configuration for a proxy host. Required: host_id (str\|int), enabled (bool). Optional: block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool), custom_blocked_agents (str, comma-separated list).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `block_bad_bots` | `bool` | — | `true` |
| `block_ai_bots` | `bool` | — | `false` |
| `allow_search_engines` | `bool` | — | `true` |
| `block_suspicious_clients` | `bool` | — | `false` |
| `challenge_suspicious` | `bool` | — | `false` |
| `disable_global` | `bool` | — | `false` |
| `custom_blocked_agents` | `str/null` | — | `null` |

#### `npg_get_proxy_host_security_headers`

GET security headers configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_update_proxy_host_security_headers`

UPDATE security headers for a proxy host. Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options (DENY/SAMEORIGIN/''), x_content_type_options, x_xss_protection, referrer_policy, content_security_policy

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `hsts_enabled` | `bool` | — | `true` |
| `hsts_max_age` | `int` | — | `31536000` |
| `hsts_include_subdomains` | `bool` | — | `true` |
| `hsts_preload` | `bool` | — | `false` |
| `x_frame_options` | `str` | — | `"SAMEORIGIN"` |
| `x_content_type_options` | `bool` | — | `true` |
| `x_xss_protection` | `bool` | — | `true` |
| `referrer_policy` | `str` | — | `"strict-origin-when-cross-origin"` |
| `content_security_policy` | `str` | — | `""` |

#### `npg_apply_security_header_preset`

APPLY a security header preset to a proxy host. preset: strict, balanced, or relaxed.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `preset` | `str` | ✔ |  |

#### `npg_get_proxy_host_upstream`

GET upstream/load balancing configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_update_proxy_host_upstream`

UPDATE upstream/load balancing configuration. Body: name, scheme, servers (list of {address, port, weight, backup}), load_balance, health_check_enabled, health_check_path, health_check_interval

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `scheme` | `str` | — | `"http"` |
| `servers` | `array<any>/null` | — | `null` |
| `load_balance` | `str` | — | `"round_robin"` |
| `health_check_enabled` | `bool` | — | `false` |
| `health_check_path` | `str` | — | `"/"` |
| `health_check_interval` | `int` | — | `10` |

#### `npg_get_proxy_host_uri_block`

GET URI block configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_update_proxy_host_uri_block`

UPDATE URI block configuration. Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `rules` | `array<any>/null` | — | `null` |
| `exception_ips` | `array<any>/null` | — | `null` |
| `allow_private_ips` | `bool` | — | `true` |

#### `npg_get_security_headers_presets`

Get available security header presets.

_매개변수 없음._

### 지역 제한(Geo Restriction) (5)

#### `npg_get_proxy_host_geo`

GET geo restriction configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_create_proxy_host_geo`

CREATE geo restriction for a proxy host. Body: enabled, mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `mode` | `str` | — | `"blacklist"` |
| `countries` | `array<any>/null` | — | `null` |
| `allowed_ips` | `array<any>/null` | — | `null` |
| `challenge_mode` | `bool` | — | `false` |

#### `npg_update_proxy_host_geo`

UPDATE geo restriction for a proxy host. Body: enabled, mode, countries, allowed_ips, challenge_mode

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `mode` | `str` | — | `"blacklist"` |
| `countries` | `array<any>/null` | — | `null` |
| `allowed_ips` | `array<any>/null` | — | `null` |
| `challenge_mode` | `bool` | — | `false` |

#### `npg_delete_proxy_host_geo`

DELETE geo restriction for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_list_countries`

List available country codes for GeoIP blocking.

_매개변수 없음._

### Fail2ban & 챌린지 (6)

#### `npg_get_proxy_host_fail2ban`

GET fail2ban configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_update_proxy_host_fail2ban`

UPDATE fail2ban configuration. Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge)

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `max_retries` | `int` | — | `5` |
| `find_time` | `int` | — | `600` |
| `ban_time` | `int` | — | `3600` |
| `fail_codes` | `str` | — | `"401,403"` |
| `action` | `str` | — | `"block"` |

#### `npg_get_proxy_host_challenge`

GET CAPTCHA/challenge configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_update_proxy_host_challenge`

UPDATE CAPTCHA/challenge configuration. Body: enabled, challenge_type (captcha/js_challenge), difficulty, site_key, token_validity, min_score, apply_to, page_title, challenge_ips

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `enabled` | `bool` | ✔ |  |
| `challenge_type` | `str` | — | `"captcha"` |
| `difficulty` | `str` | — | `"medium"` |
| `site_key` | `str` | — | `""` |
| `token_validity` | `int` | — | `86400` |
| `min_score` | `num` | — | `0.5` |
| `apply_to` | `str` | — | `"both"` |
| `page_title` | `str` | — | `"Security Check"` |

#### `npg_delete_proxy_host_challenge`

DELETE CAPTCHA/challenge configuration for a proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_verify_challenge`

Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `token` | `str` | ✔ |  |
| `solution` | `str` | ✔ |  |

### 액세스 목록(Access Lists) (5)

#### `npg_list_access_lists`

List all access lists (authentication/restriction lists).

_매개변수 없음._

#### `npg_get_access_list`

Get an access list by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `list_id` | `str/int` | ✔ |  |

#### `npg_create_access_list`

Create a new access list. Required: name, advanced_config (block/allow rules).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `name` | `str` | ✔ |  |
| `advanced_config` | `str` | — | `""` |
| `clients` | `array<any>/null` | — | `null` |

#### `npg_update_access_list`

Update an access list. Pass only fields to change.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `list_id` | `str/int` | ✔ |  |
| `name` | `str/null` | — | `null` |
| `advanced_config` | `str/null` | — | `null` |
| `clients` | `array<any>/null` | — | `null` |

#### `npg_delete_access_list`

Delete an access list by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `list_id` | `str/int` | ✔ |  |

### DNS 제공자(DNS Providers) (6)

#### `npg_list_dns_providers`

List all DNS providers configured for DNS-01 challenges.

_매개변수 없음._

#### `npg_get_dns_provider`

Get a DNS provider by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `provider_id` | `str/int` | ✔ |  |

#### `npg_create_dns_provider`

Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `name` | `str` | ✔ |  |
| `provider_type` | `str` | ✔ |  |
| `credentials` | `obj/null` | — | `null` |
| `kwargs` | `obj/null` | — | `null` |

#### `npg_update_dns_provider`

Update a DNS provider. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `provider_id` | `str/int` | ✔ |  |
| `kwargs` | `obj/null` | — | `null` |

#### `npg_delete_dns_provider`

Delete a DNS provider by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `provider_id` | `str/int` | ✔ |  |

#### `npg_test_dns_provider`

Test DNS provider credentials.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `provider_id` | `str/int` | ✔ |  |

### 클라우드 제공자(Cloud Providers) (5)

#### `npg_list_cloud_providers`

List all cloud providers (for certificate DNS challenges).

_매개변수 없음._

#### `npg_get_cloud_provider`

Get a cloud provider by its slug.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `slug` | `str` | ✔ |  |

#### `npg_create_cloud_provider`

Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `name` | `str` | ✔ |  |
| `slug` | `str` | ✔ |  |
| `ip_ranges` | `array<str>` | ✔ |  |
| `region` | `str/null` | — | `null` |
| `description` | `str/null` | — | `null` |
| `kwargs` | `obj/null` | — | `null` |

#### `npg_update_cloud_provider`

Update a cloud provider by its slug. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `slug` | `str` | ✔ |  |
| `kwargs` | `obj/null` | — | `null` |

#### `npg_delete_cloud_provider`

Delete a cloud provider by its slug.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `slug` | `str` | ✔ |  |

### GeoIP (2)

#### `npg_get_geoip_status`

Get GeoIP database update status.

_매개변수 없음._

#### `npg_update_geoip`

Update GeoIP databases.

_매개변수 없음._

### 차단 IP & 봇(Banned IPs & Bots) (4)

#### `npg_list_banned_ips`

List banned IP addresses.

_매개변수 없음._

#### `npg_ban_ip`

Ban an IP address. Required: ip. Optional: ban_time (seconds).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `ip_address` | `str` | ✔ |  |
| `reason` | `str` | — | `"Manual ban via API"` |
| `duration` | `int` | — | `3600` |

#### `npg_unban_ip`

Unban an IP by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `ip_id` | `str/int` | ✔ |  |

#### `npg_get_bots_known`

Get list of known bot user-agent signatures.

_매개변수 없음._

### URI 차단(URI Block) (2)

#### `npg_get_global_uri_block`

Get global URI block settings.

_매개변수 없음._

#### `npg_update_global_uri_block`

Update global URI block settings. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `kwargs` | `obj/null` | — | `null` |

### WAF & 악성 규칙(WAF & Exploit Rules) (10)

#### `npg_list_exploit_rules`

List exploit block rules.

_매개변수 없음._

#### `npg_get_exploit_rule`

Get an exploit rule by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `rule_id` | `str/int` | ✔ |  |

#### `npg_create_exploit_rule`

Create an exploit block rule. Required: category, name, pattern, pattern_type (e.g. 'query_string'). Optional: severity, description.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `category` | `str` | ✔ |  |
| `name` | `str` | ✔ |  |
| `pattern` | `str` | ✔ |  |
| `pattern_type` | `str` | ✔ |  |
| `severity` | `str/null` | — | `null` |
| `description` | `str/null` | — | `null` |
| `kwargs` | `obj/null` | — | `null` |

#### `npg_update_exploit_rule`

Update an exploit rule. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `rule_id` | `str/int` | ✔ |  |
| `kwargs` | `obj/null` | — | `null` |

#### `npg_delete_exploit_rule`

Delete an exploit rule by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `rule_id` | `str/int` | ✔ |  |

#### `npg_toggle_exploit_rule`

Toggle an exploit rule's enabled status.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `rule_id` | `str/int` | ✔ |  |

#### `npg_list_waf_rules`

List all WAF (Web Application Firewall) rules.

_매개변수 없음._

#### `npg_get_waf_hosts`

Get WAF config for all proxy hosts.

_매개변수 없음._

#### `npg_get_waf_host_config`

Get WAF config for a specific proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |

#### `npg_disable_waf_rule`

Disable a WAF rule for a specific proxy host.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `host_id` | `str/int` | ✔ |  |
| `rule_id` | `str/int` | ✔ |  |

### 설정(Settings) (4)

#### `npg_get_settings`

Get global NPG settings.

_매개변수 없음._

#### `npg_update_settings`

Update global NPG settings. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `kwargs` | `obj/null` | — | `null` |

#### `npg_get_system_settings`

Get system settings (server name, timezone, locale).

_매개변수 없음._

#### `npg_update_system_settings`

Update system settings. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `kwargs` | `obj/null` | — | `null` |

### 로그(Logs) (6)

#### `npg_get_logs`

Get access logs.

_매개변수 없음._

#### `npg_get_log_settings`

Get log settings.

_매개변수 없음._

#### `npg_update_log_settings`

Update log settings. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `kwargs` | `obj/null` | — | `null` |

#### `npg_get_log_stats`

Get log statistics.

_매개변수 없음._

#### `npg_list_audit_logs`

List audit log entries.

_매개변수 없음._

#### `npg_list_system_logs`

List system logs.

_매개변수 없음._

### 백업(Backups) (5)

#### `npg_list_backups`

List all backups.

_매개변수 없음._

#### `npg_get_backup`

Get a backup by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `backup_id` | `str/int` | ✔ |  |

#### `npg_create_backup`

Create a new backup.

_매개변수 없음._

#### `npg_delete_backup`

Delete a backup by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `backup_id` | `str/int` | ✔ |  |

#### `npg_restore_backup`

Restore from a backup. Required: backup_id.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `backup_id` | `str/int` | ✔ |  |

### API 토큰(API Tokens) (6)

#### `npg_list_api_tokens`

List all API tokens.

_매개변수 없음._

#### `npg_get_api_token`

Get an API token by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `token_id` | `str/int` | ✔ |  |

#### `npg_create_api_token`

Create a new API token. Required: name, permissions (array). Optional: expires_at.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `name` | `str` | ✔ |  |
| `permissions` | `array<str>` | ✔ |  |
| `expires_at` | `str/null` | — | `null` |

#### `npg_update_api_token`

Update an API token. Pass only fields to change (dict).

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `token_id` | `str/int` | ✔ |  |
| `kwargs` | `obj/null` | — | `null` |

#### `npg_revoke_api_token`

Revoke an API token by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `token_id` | `str/int` | ✔ |  |

#### `npg_delete_api_token`

Delete an API token by its ID.

| 매개변수 | 유형 | 필수 | 기본값 |
|---------|------|:---:|--------|
| `token_id` | `str/int` | ✔ |  |

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
  main.py       # 105개의 모든 MCP 도구
  client.py     # 자동 인증을 갖춘 HTTP 클라이언트 래퍼
  __init__.py
Dockerfile      # Multi-stage Docker 빌드
docker-compose.yml
pyproject.toml  # 의존성: mcp>=1.0, httpx>=0.27
```

## 라이선스

MIT

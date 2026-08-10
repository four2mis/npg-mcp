# NPG MCP Server

**English** | [한국어](README.ko.md)

MCP server for [NginxProxyGuard](https://github.com/svrforum/NginxProxyGuard) (NPG) — manage proxy hosts, certificates, SSL, security rules, and nginx configuration through MCP tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org).

> **⚠️ Vibe-coded with an AI agent.** This codebase was generated at speed by an AI agent, not hand-crafted by a human. Expect rough edges, unhandled edge cases, and bugs. Do **not** deploy it to an active/production NginxProxyGuard instance without first testing against a **sandboxed / disposable NPG environment** and reviewing the code. It can create, update, delete, and reconfigure live proxy hosts, so verify in isolation before pointing it at real infrastructure.

## Tools Reference

This server exposes **282 MCP tools**. Each tool is documented below with a short description and its **input parameter schema** (parameter, type, whether it is required, and default value). Tools are grouped into the following categories:

- **Proxy Hosts** — 38 tools
- **Logs** — 37 tools
- **Security & WAF** — 32 tools
- **DNS Providers** — 15 tools
- **Authentication** — 15 tools
- **Certificates** — 12 tools
- **Filter Subscriptions** — 12 tools
- **Cloud Providers** — 11 tools
- **URI Block** — 10 tools
- **Settings** — 8 tools
- **Backups** — 8 tools
- **API Tokens** — 8 tools
- **Users** — 8 tools
- **SSO Providers** — 7 tools
- **Other** — 6 tools
- **Dashboard** — 6 tools
- **IP Management** — 6 tools
- **Notification Channels** — 6 tools
- **Redirect Hosts** — 5 tools
- **Access Lists** — 5 tools
- **Geo** — 5 tools
- **Fail2ban & Challenge** — 4 tools
- **Banned IPs & Bots** — 4 tools
- **Roles** — 4 tools
- **System** — 4 tools
- **SSL / Nginx** — 3 tools
- **System & Health** — 2 tools
- **Docker** — 1 tools

### Proxy Hosts (38)

#### `npg_list_proxy_hosts`

List all proxy hosts. Returns a list of proxy host objects.

_No parameters._

---

#### `npg_get_proxy_host`

Get a single proxy host by its ID.

_No parameters._

---

#### `npg_get_proxy_host_by_domain`

Get a proxy host by its domain name.

_No parameters._

---

#### `npg_create_proxy_host`

Create a new reverse proxy host. Required: domain_names (array), forward_host, forward_port. Optional: pass only the fields you want to change; omitted fields inherit global defaults or sensible built-in defaults. Fields: proxy_type (default 'http'), forward_scheme (default 'http'), enabled (default True), ssl_enabled, ssl_forced (default True), ssl_http2 (default True), ssl_http3, ssl_cert_id, waf_enabled, waf_use_global (default True), waf_paranoia_level, waf_anomaly_threshold, waf_mode, cache_enabled, cache_static_only, cache_ttl, cache_template, block_normal, block_http, block_exploits (default True), block_exploits_exceptions, allow_websocket_upgrade (default True), enable_proxy_headers, host_header, extra_domains, advanced_config, proxy_buffering (str), proxy_request_buffering (str), client_max_body_size (str), proxy_max_temp_file_size (str), proxy_connect/send/read_timeout, access_list_id, auth_provider_id, auth_bypass_paths, ddns_enabled/provider_id/proxied, forward_container_name/network, stream_* fields.

_No parameters._

---

#### `npg_update_proxy_host`

Update an existing proxy host (partial update — pass only the fields you want to change; omitted fields are left as-is). Use `skip_nginx=true` to skip nginx regeneration. Fields: domain_names, forward_host, forward_port, forward_scheme, block_normal, waf_enabled, waf_use_global (bool | None — tri-state: omit=leave unchanged, false=host own WAF config, true=inherit global WAF), waf_paranoia_level, waf_anomaly_threshold, block_http, ssl_forced, ssl_cert_id, cache_enabled, cache_static_only, cache_ttl (str), cache_template, advanced_config, enable_proxy_headers, host_header, extra_domains, enabled, ssl_http2, ssl_http3, block_exploits, block_exploits_exceptions, allow_websocket_upgrade, proxy_connect/send/read_timeout, proxy_buffering (str: 'on'/'off'/''), proxy_request_buffering (str: 'on'/'off'/''), client_max_body_size (str, e.g. '10m'/'off'), proxy_max_temp_file_size (str), access_list_id, auth_provider_id, auth_bypass_paths (list[str]), ddns_enabled/provider_id/proxied, forward_container_name/network. Nullable id fields (certificate_id, access_list_id, auth_provider_id, ddns_provider_id, forward_container_name/network): empty string clears, omitted leaves unchanged; auth_bypass_paths: [] clears.

_No parameters._

---

#### `npg_delete_proxy_host`

Delete a proxy host by its ID.

_No parameters._

---

#### `npg_test_proxy_host`

Test upstream connectivity for a proxy host.

_No parameters._

---

#### `npg_sync_proxy_hosts`

Sync all proxy host configs and reload nginx.

_No parameters._

---

#### `npg_clone_proxy_host`

Clone a proxy host with new domain names. Returns the new proxy host.

_No parameters._

---

#### `npg_get_proxy_host_rate_limit`

GET rate limit configuration for a proxy host.

_No parameters._

---

#### `npg_update_proxy_host_rate_limit`

UPDATE rate limit configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), requests_per_second (int), burst_size (int), zone_size (str), limit_by (str: ip/uri/ip_uri), limit_response (int), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global)

_No parameters._

---

#### `npg_get_proxy_host_bot_filter`

GET bot filter configuration for a proxy host.

_No parameters._

---

#### `npg_update_proxy_host_bot_filter`

UPDATE bot filter configuration for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Required: host_id (str|int). Optional: enabled (bool), block_bad_bots (bool), block_ai_bots (bool), allow_search_engines (bool), block_suspicious_clients (bool), challenge_suspicious (bool), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), custom_blocked_agents (str, comma-separated list), custom_allowed_agents (str, comma-separated list).

_No parameters._

---

#### `npg_get_proxy_host_security_headers`

GET security headers configuration for a proxy host.

_No parameters._

---

#### `npg_update_proxy_host_security_headers`

UPDATE security headers for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), hsts_enabled (bool), hsts_max_age (int), hsts_include_subdomains (bool), hsts_preload (bool), x_frame_options (str: DENY/SAMEORIGIN/''), x_content_type_options (bool), x_xss_protection (bool), referrer_policy (str), content_security_policy (str), disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global)

_No parameters._

---

#### `npg_get_proxy_host_upstream`

GET upstream/load balancing configuration for a proxy host.

_No parameters._

---

#### `npg_update_proxy_host_upstream`

UPDATE upstream/load balancing configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: scheme, servers (list of {address, port, weight, backup}), load_balance, health_check_enabled, health_check_path, health_check_interval.

_No parameters._

---

#### `npg_get_proxy_host_uri_block`

GET URI block configuration for a proxy host.

_No parameters._

---

#### `npg_update_proxy_host_uri_block`

UPDATE URI block configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips.

_No parameters._

---

#### `npg_get_proxy_host_cloud_blocking`

GET per-host cloud provider blocking configuration. Returns blocked_providers, challenge_mode, allow_search_bots, cloud_disable_global.

_No parameters._

---

#### `npg_update_proxy_host_cloud_blocking`

UPDATE per-host cloud provider blocking (the endpoint full-replaces all fields, so the tool reads current settings and merges — omitted fields are left as-is). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool), cloud_disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global).

_No parameters._

---

#### `npg_get_proxy_host_geo`

GET geo restriction configuration for a proxy host.

_No parameters._

---

#### `npg_create_proxy_host_geo`

CREATE geo restriction for a proxy host. Required: host_id, countries (list of ISO codes, min 1). Optional: mode (whitelist/blacklist, default blacklist), allowed_ips, challenge_mode, disable_global (bool — false=inherit, true=disable global), allow_private_ips, allow_search_bots

_No parameters._

---

#### `npg_update_proxy_host_geo`

UPDATE geo restriction for a proxy host (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, challenge_mode, disable_global (bool | None — tri-state: omit=inherit global default, false=inherit, true=disable/opt out of global), allow_private_ips, allow_search_bots

_No parameters._

---

#### `npg_delete_proxy_host_geo`

DELETE geo restriction for a proxy host.

_No parameters._

---

#### `npg_get_proxy_host_fail2ban`

GET fail2ban configuration for a proxy host.

_No parameters._

---

#### `npg_update_proxy_host_fail2ban`

UPDATE fail2ban configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, max_retries, find_time (seconds), ban_time (seconds), fail_codes, action (block/challenge).

_No parameters._

---

#### `npg_get_proxy_host_challenge`

GET CAPTCHA/challenge configuration for a proxy host.

_No parameters._

---

#### `npg_update_proxy_host_challenge`

UPDATE CAPTCHA/challenge configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled (bool), challenge_type (str), site_key (str), token_validity (int), min_score (float), apply_to (str), page_title (str)

_No parameters._

---

#### `npg_delete_proxy_host_challenge`

DELETE CAPTCHA/challenge configuration for a proxy host.

_No parameters._

---

#### `npg_set_proxy_host_favorite`

Toggle a proxy host as a favorite. REQUIRED: host_id, favorite (bool).

_No parameters._

---

#### `npg_delete_proxy_host_bot_filter`

Delete the bot filter config for a proxy host — host falls back to global default. REQUIRED: host_id.

_No parameters._

---

#### `npg_delete_proxy_host_security_headers`

Delete the security headers config for a proxy host — host falls back to global default. REQUIRED: host_id.

_No parameters._

---

#### `npg_delete_proxy_host_upstream`

Delete the upstream/load balancing config for a proxy host — host falls back to defaults. REQUIRED: host_id.

_No parameters._

---

#### `npg_delete_proxy_host_uri_block`

Delete the URI block config for a proxy host — host falls back to global default. REQUIRED: host_id.

_No parameters._

---

#### `npg_delete_proxy_host_fail2ban`

Delete the fail2ban config for a proxy host — host falls back to global default. REQUIRED: host_id.

_No parameters._

---

#### `npg_add_proxy_host_uri_block_rule`

Add a single URI block rule to a proxy host. REQUIRED: host_id, path (str or regex), action (block/allow). Optional: case_sensitive (bool).

_No parameters._

---

#### `npg_delete_proxy_host_uri_block_rule`

Remove a single URI block rule from a proxy host. REQUIRED: host_id, rule_id.

_No parameters._

---

### Logs (37)

#### `npg_get_logs`

Get access logs.

_No parameters._

---

#### `npg_get_log_settings`

Get log settings.

_No parameters._

---

#### `npg_update_log_settings`

Update log settings. Pass only fields to change (dict).

_No parameters._

---

#### `npg_get_log_stats`

Get log statistics.

_No parameters._

---

#### `npg_list_audit_logs`

List audit log entries.

_No parameters._

---

#### `npg_list_system_logs`

List system logs.

_No parameters._

---

#### `npg_list_log_files`

List all log files.

_No parameters._

---

#### `npg_download_log_file`

Download a log file by its filename.

_No parameters._

---

#### `npg_view_log_file`

View the contents of a log file.

_No parameters._

---

#### `npg_rotate_log_file`

Rotate a log file by its filename.

_No parameters._

---

#### `npg_delete_log_file`

Delete a log file by its filename.

_No parameters._

---

#### `npg_get_catalog`

Get the exploit block rule catalog.

_No parameters._

---

#### `npg_subscribe_catalog`

Subscribe to a catalog entry. Required: catalog_id.

_No parameters._

---

#### `npg_get_filter_subscription_catalog`

Get the curated filter catalog — list of available filter lists to subscribe to.

_No parameters._

---

#### `npg_subscribe_filter_catalog`

Subscribe to one or more catalog filter lists. REQUIRED: catalog_ids (list of catalog IDs).

_No parameters._

---

#### `npg_get_certificate_logs`

Get the issuance log stream for a certificate. REQUIRED: cert_id.

_No parameters._

---

#### `npg_post_log`

Insert a log entry manually. REQUIRED: level, message. Optional: source, component, tags.

_No parameters._

---

#### `npg_cleanup_logs`

Delete nginx access logs older than the configured retention period.

_No parameters._

---

#### `npg_get_log_autocomplete_hosts`

Get distinct hosts seen in nginx access logs (for autocomplete).

_No parameters._

---

#### `npg_get_log_autocomplete_ips`

Get distinct client IPs seen in nginx access logs (for autocomplete).

_No parameters._

---

#### `npg_get_log_autocomplete_user_agents`

Get distinct User-Agents seen in nginx access logs (for autocomplete).

_No parameters._

---

#### `npg_get_log_autocomplete_uris`

Get distinct request URIs seen in nginx access logs (for autocomplete).

_No parameters._

---

#### `npg_get_log_autocomplete_countries`

Get distinct countries seen in nginx access logs (for autocomplete).

_No parameters._

---

#### `npg_get_log_autocomplete_methods`

Get distinct HTTP methods seen in nginx access logs (for autocomplete).

_No parameters._

---

#### `npg_get_log_filter_presets`

List saved log filter presets.

_No parameters._

---

#### `npg_create_log_filter_preset`

Save a log filter preset. REQUIRED: name, filter (dict). Optional: description.

_No parameters._

---

#### `npg_update_log_filter_preset`

Update a log filter preset (rename and/or replace filter). REQUIRED: preset_id. Optional: name, filter, description.

_No parameters._

---

#### `npg_delete_log_filter_preset`

Delete a log filter preset by its ID.

_No parameters._

---

#### `npg_cleanup_system_logs`

Delete old system logs beyond the configured retention period.

_No parameters._

---

#### `npg_get_system_log_sources`

Get selectable system log sources (docker_api, docker_nginx, health_check, etc.).

_No parameters._

---

#### `npg_get_system_log_levels`

Get selectable system log levels (debug, info, warn, error, fatal).

_No parameters._

---

#### `npg_get_system_log_stats`

Get system log statistics (counts by source/level).

_No parameters._

---

#### `npg_get_system_settings_logs`

Get the container log collector configuration.

_No parameters._

---

#### `npg_update_system_settings_logs`

Update the container log collector configuration (partial update). Pass only fields to change.

_No parameters._

---

#### `npg_get_audit_log_actions`

List the action values present in the audit log (for filtering).

_No parameters._

---

#### `npg_get_audit_log_resource_types`

List the resource types present in the audit log (for filtering).

_No parameters._

---

#### `npg_get_audit_log_api_tokens`

List recent API token usage across all tokens.

_No parameters._

---

### Security & WAF (32)

#### `npg_apply_security_header_preset`

APPLY a security header preset to a proxy host. preset: strict, balanced, or relaxed.

_No parameters._

---

#### `npg_get_security_headers_presets`

Get available security header presets.

_No parameters._

---

#### `npg_list_exploit_rules`

List exploit block rules.

_No parameters._

---

#### `npg_get_exploit_rule`

Get an exploit rule by its ID.

_No parameters._

---

#### `npg_create_exploit_rule`

Create an exploit block rule. Required: category, name, pattern, pattern_type (e.g. 'query_string'). Optional: severity, description.

_No parameters._

---

#### `npg_update_exploit_rule`

Update an exploit rule. Pass only fields to change (dict).

_No parameters._

---

#### `npg_delete_exploit_rule`

Delete an exploit rule by its ID.

_No parameters._

---

#### `npg_toggle_exploit_rule`

Toggle an exploit rule's enabled status.

_No parameters._

---

#### `npg_list_waf_rules`

List all WAF (Web Application Firewall) rules.

_No parameters._

---

#### `npg_get_waf_hosts`

Get WAF config for all proxy hosts.

_No parameters._

---

#### `npg_get_waf_host_config`

Get WAF config for a specific proxy host.

_No parameters._

---

#### `npg_disable_waf_rule`

Disable a WAF rule for a specific proxy host.

_No parameters._

---

#### `npg_get_global_security_headers`

GET global security headers configuration.

_No parameters._

---

#### `npg_update_global_security_headers`

UPDATE global security headers configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, hsts_enabled, hsts_max_age, hsts_include_subdomains, hsts_preload, x_frame_options, x_content_type_options, x_xss_protection, referrer_policy, content_security_policy.

_No parameters._

---

#### `npg_get_global_waf`

GET global WAF configuration.

_No parameters._

---

#### `npg_update_global_waf`

UPDATE global WAF configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, paranoia_level, anomaly_threshold, rules (list of {id, enabled}).

_No parameters._

---

#### `npg_get_exploit_rules_hosts`

List proxy hosts that have exploit blocking enabled.

_No parameters._

---

#### `npg_get_exploit_rules_for_host`

List exploit rules with this host's exclusion status. REQUIRED: host_id.

_No parameters._

---

#### `npg_exclude_exploit_rule_from_host`

Exclude an exploit rule on ONE proxy host (stop it blocking there). REQUIRED: host_id, rule_id.

_No parameters._

---

#### `npg_remove_exploit_rule_exclusion_from_host`

Remove a host exclusion for an exploit rule (re-enable the rule for that host). REQUIRED: host_id, rule_id.

_No parameters._

---

#### `npg_global_exclude_exploit_rule`

Exclude an exploit rule on EVERY host (stop it blocking anywhere). REQUIRED: rule_id.

_No parameters._

---

#### `npg_remove_exploit_rule_global_exclusion`

Remove a global exclusion for an exploit rule (re-enable the rule everywhere). REQUIRED: rule_id.

_No parameters._

---

#### `npg_get_waf_global_rules`

List all OWASP CRS rules with their GLOBAL exclusion status.

_No parameters._

---

#### `npg_get_waf_global_exclusions`

List the globally disabled CRS rules.

_No parameters._

---

#### `npg_get_waf_global_history`

Get the global WAF policy change history.

_No parameters._

---

#### `npg_disable_waf_global_rule`

Disable a CRS rule for EVERY host (globally). REQUIRED: rule_id.

_No parameters._

---

#### `npg_enable_waf_global_rule`

Re-enable a CRS rule globally (remove global disable). REQUIRED: rule_id.

_No parameters._

---

#### `npg_get_waf_host_history`

Get the WAF policy change history for a proxy host. REQUIRED: host_id.

_No parameters._

---

#### `npg_disable_waf_rule_by_host`

Disable a CRS rule on the host that owns a domain name. REQUIRED: domain_name, rule_id.

_No parameters._

---

#### `npg_get_waf_test_patterns`

List the built-in WAF attack test patterns.

_No parameters._

---

#### `npg_test_waf_pattern`

Fire one attack payload at a target URL for WAF testing. REQUIRED: target_url, pattern (pattern name or index).

_No parameters._

---

#### `npg_test_waf_all_patterns`

Fire every attack payload at a target URL for comprehensive WAF testing. REQUIRED: target_url.

_No parameters._

---

### DNS Providers (15)

#### `npg_list_dns_providers`

List all DNS providers configured for DNS-01 challenges.

_No parameters._

---

#### `npg_get_dns_provider`

Get a DNS provider by its ID.

_No parameters._

---

#### `npg_create_dns_provider`

Create a DNS provider for DNS-01 challenges. Required: name, provider_type (e.g. 'cloudflare'), credentials (dict, e.g. {'api_token': '...'}).

_No parameters._

---

#### `npg_update_dns_provider`

Update a DNS provider. Pass only fields to change (dict).

_No parameters._

---

#### `npg_delete_dns_provider`

Delete a DNS provider by its ID.

_No parameters._

---

#### `npg_test_dns_provider`

Test DNS provider credentials.

_No parameters._

---

#### `npg_list_ddns_records`

List all DDNS records.

_No parameters._

---

#### `npg_create_ddns_record`

Create a DDNS record. REQUIRED: proxy_host_id, domain, provider_id. Optional: proxied (bool).

_No parameters._

---

#### `npg_get_ddns_record`

Get a DDNS record by its ID.

_No parameters._

---

#### `npg_update_ddns_record`

Update a DDNS record (partial update). Pass only fields to change.

_No parameters._

---

#### `npg_delete_ddns_record`

Delete a DDNS record by its ID.

_No parameters._

---

#### `npg_sync_ddns_records`

Sync all enabled DDNS records now (force immediate DNS update for all records).

_No parameters._

---

#### `npg_sync_ddns_record`

Sync one DDNS record now (force DNS update for a specific record). REQUIRED: record_id.

_No parameters._

---

#### `npg_import_ddns_from_hosts`

Import DDNS records from existing proxy hosts that have DDNS enabled.

_No parameters._

---

#### `npg_get_dns_provider_default`

Get the default DNS provider for certificate issuance.

_No parameters._

---

### Authentication (15)

#### `npg_get_auth_status`

GET authentication status — returns whether the current session is authenticated and basic user info.

_No parameters._

---

#### `npg_get_auth_account`

GET own account info — returns the authenticated user's account details.

_No parameters._

---

#### `npg_auth_change_credentials`

Change own username and password (initial setup). REQUIRED: current_password, new_username, new_password. Used to complete forced initial setup.

_No parameters._

---

#### `npg_auth_2fa_setup`

Begin 2FA enrolment — returns QR code / secret for the user to scan with their authenticator app.

_No parameters._

---

#### `npg_auth_2fa_enable`

Enable 2FA. REQUIRED: password, totp_code (6-digit code from authenticator).

_No parameters._

---

#### `npg_auth_2fa_disable`

Disable 2FA. REQUIRED: password, totp_code.

_No parameters._

---

#### `npg_get_auth_language`

GET the authenticated user's UI language preference.

_No parameters._

---

#### `npg_update_auth_language`

SET the authenticated user's UI language. REQUIRED: language (e.g. 'en', 'ko').

_No parameters._

---

#### `npg_get_auth_font`

GET the authenticated user's UI font family preference.

_No parameters._

---

#### `npg_update_auth_font`

SET the authenticated user's UI font family. REQUIRED: font (e.g. 'Inter', 'Roboto').

_No parameters._

---

#### `npg_list_auth_providers`

List ForwardAuth (Authelia, Authentik, custom) providers.

_No parameters._

---

#### `npg_create_auth_provider`

Create a ForwardAuth provider. REQUIRED: name, type, config dict (provider-specific).

_No parameters._

---

#### `npg_get_auth_provider`

Get a ForwardAuth provider by its ID.

_No parameters._

---

#### `npg_update_auth_provider`

Update a ForwardAuth provider (partial update). Pass only fields to change.

_No parameters._

---

#### `npg_delete_auth_provider`

Delete a ForwardAuth provider by its ID.

_No parameters._

---

### Certificates (12)

#### `npg_list_certificates`

List all SSL/TLS certificates.

_No parameters._

---

#### `npg_get_certificate`

Get a certificate by its ID.

_No parameters._

---

#### `npg_create_certificate`

Request a new Let's Encrypt certificate. Required: domain_names (array), email. Optional: provider (e.g. 'letsencrypt'), dns_provider_id, etc.

_No parameters._

---

#### `npg_delete_certificate`

Delete a certificate by its ID.

_No parameters._

---

#### `npg_renew_certificate`

Renew a certificate by its ID.

_No parameters._

---

#### `npg_get_expiring_certificates`

Get certificates that are expiring soon.

_No parameters._

---

#### `npg_get_certificate_history`

Get certificate history.

_No parameters._

---

#### `npg_upload_certificate`

Upload a certificate file. Required: domain_names, cert_content, key_content.

_No parameters._

---

#### `npg_delete_certificate_errors`

Bulk-delete all certificates in error status.

_No parameters._

---

#### `npg_clear_certificate_error`

Clear a certificate's error state (mark as resolved). REQUIRED: cert_id.

_No parameters._

---

#### `npg_upload_certificate_pem`

Replace the PEM material of a custom certificate. REQUIRED: cert_id, pem_content (full PEM string).

_No parameters._

---

#### `npg_get_certificate_download`

Download certificate material (PEM). REQUIRED: cert_id.

_No parameters._

---

### Filter Subscriptions (12)

#### `npg_list_filter_subscriptions`

List all filter subscriptions (remote IP/UA blocklists).

_No parameters._

---

#### `npg_create_filter_subscription`

Subscribe to a filter list URL. REQUIRED: url. Optional: name.

_No parameters._

---

#### `npg_get_filter_subscription`

Get a filter subscription with its entries and exclusions. REQUIRED: subscription_id.

_No parameters._

---

#### `npg_update_filter_subscription`

Update a filter subscription (partial update). Pass only fields to change.

_No parameters._

---

#### `npg_delete_filter_subscription`

Delete a filter subscription by its ID.

_No parameters._

---

#### `npg_refresh_filter_subscription`

Re-fetch entries for a filter subscription now. REQUIRED: subscription_id.

_No parameters._

---

#### `npg_get_filter_subscription_exclusions`

List host exclusions of a filter subscription (hosts that skip this subscription). REQUIRED: subscription_id.

_No parameters._

---

#### `npg_add_filter_subscription_exclusion`

Exclude a proxy host from a filter subscription. REQUIRED: subscription_id, host_id.

_No parameters._

---

#### `npg_remove_filter_subscription_exclusion`

Remove a host exclusion from a filter subscription. REQUIRED: subscription_id, host_id.

_No parameters._

---

#### `npg_get_filter_subscription_entry_exclusions`

List entry exclusions of a filter subscription (specific entries that are skipped). REQUIRED: subscription_id.

_No parameters._

---

#### `npg_add_filter_subscription_entry_exclusion`

Exclude a single entry value from a filter subscription. REQUIRED: subscription_id, entry_value.

_No parameters._

---

#### `npg_remove_filter_subscription_entry_exclusion`

Remove an entry exclusion from a filter subscription. REQUIRED: subscription_id, entry_value.

_No parameters._

---

### Cloud Providers (11)

#### `npg_list_cloud_providers`

List all cloud providers (for certificate DNS challenges).

_No parameters._

---

#### `npg_get_cloud_provider`

Get a cloud provider by its slug.

_No parameters._

---

#### `npg_create_cloud_provider`

Create a cloud provider (IP-range database entry). Required: name, slug, ip_ranges (list of CIDR). Optional: region, description.

_No parameters._

---

#### `npg_update_cloud_provider`

Update a cloud provider by its slug. Pass only fields to change (dict).

_No parameters._

---

#### `npg_delete_cloud_provider`

Delete a cloud provider by its slug.

_No parameters._

---

#### `npg_list_cloud_providers_by_region`

List cloud providers filtered by region.

_No parameters._

---

#### `npg_get_cloudflare_tunnel`

Get Cloudflare Tunnel configuration.

_No parameters._

---

#### `npg_update_cloudflare_tunnel`

Update Cloudflare Tunnel configuration. Pass only fields to change.

_No parameters._

---

#### `npg_get_cloudflare_tunnel_status`

Get Cloudflare Tunnel status.

_No parameters._

---

#### `npg_get_global_cloud_providers`

GET global cloud providers configuration.

_No parameters._

---

#### `npg_update_global_cloud_providers`

UPDATE global cloud providers configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: blocked_providers (list of slugs), challenge_mode (bool), allow_search_bots (bool).

_No parameters._

---

### URI Block (10)

#### `npg_list_uri_blocks`

List all URI blocks (global and per-host).

_No parameters._

---

#### `npg_create_uri_block`

Create a URI block for a proxy host. Required: host_id, pattern, action (block/allow). Optional: is_regex.

_No parameters._

---

#### `npg_get_uri_block`

Get a URI block by its ID.

_No parameters._

---

#### `npg_update_uri_block`

Update a URI block. Pass only fields to change.

_No parameters._

---

#### `npg_delete_uri_block`

Delete a URI block by its ID.

_No parameters._

---

#### `npg_bulk_add_uri_block_rule`

Bulk add URI block rules. Required: rules (list of {pattern, action, is_regex}).

_No parameters._

---

#### `npg_get_global_uri_block`

GET global URI block configuration.

_No parameters._

---

#### `npg_update_global_uri_block`

UPDATE global URI block configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, rules (list of {pattern, is_regex, action}), exception_ips, allow_private_ips.

_No parameters._

---

#### `npg_add_global_uri_block_rule`

Add a rule to the global URI block. Required: pattern, action. Optional: is_regex.

_No parameters._

---

#### `npg_delete_global_uri_block_rule`

Delete a rule from the global URI block by its ID.

_No parameters._

---

### Settings (8)

#### `npg_get_settings`

Get global NPG settings.

_No parameters._

---

#### `npg_update_settings`

Update global NPG settings. Pass only fields to change (dict).

_No parameters._

---

#### `npg_get_system_settings`

Get system settings (server name, timezone, locale).

_No parameters._

---

#### `npg_update_system_settings`

Update system settings. Pass only fields to change (dict).

_No parameters._

---

#### `npg_get_public_ui_settings`

Get public UI settings (accessible without auth).

_No parameters._

---

#### `npg_reset_settings`

Reset global nginx settings to defaults. DESTRUCTIVE — this clears all custom settings.

_No parameters._

---

#### `npg_get_settings_presets`

List available global settings presets that can be applied.

_No parameters._

---

#### `npg_apply_settings_preset`

Apply a global settings preset. REQUIRED: preset (preset name/identifier).

_No parameters._

---

### Backups (8)

#### `npg_list_backups`

List all backups.

_No parameters._

---

#### `npg_get_backup`

Get a backup by its ID.

_No parameters._

---

#### `npg_create_backup`

Create a new backup.

_No parameters._

---

#### `npg_delete_backup`

Delete a backup by its ID.

_No parameters._

---

#### `npg_restore_backup`

Restore from a backup. Required: backup_id.

_No parameters._

---

#### `npg_download_backup`

Download a backup by its ID.

_No parameters._

---

#### `npg_upload_restore_backup`

Upload and restore from a backup file.

_No parameters._

---

#### `npg_get_backup_stats`

Get backup statistics.

_No parameters._

---

### API Tokens (8)

#### `npg_list_api_tokens`

List all API tokens.

_No parameters._

---

#### `npg_get_api_token`

Get an API token by its ID.

_No parameters._

---

#### `npg_create_api_token`

Create a new API token. Required: name, permissions (array). Optional: expires_at.

_No parameters._

---

#### `npg_update_api_token`

Update an API token. Pass only fields to change (dict).

_No parameters._

---

#### `npg_revoke_api_token`

Revoke an API token by its ID.

_No parameters._

---

#### `npg_delete_api_token`

Delete an API token by its ID.

_No parameters._

---

#### `npg_get_api_token_permissions`

List the permission strings an API token may carry (reference list).

_No parameters._

---

#### `npg_get_api_token_usage`

Get recent usage for an API token. REQUIRED: token_id.

_No parameters._

---

### Users (8)

#### `npg_list_users`

List all users.

_No parameters._

---

#### `npg_get_user`

Get a user by their ID.

_No parameters._

---

#### `npg_create_user`

Create a new user. Required: username, email, password. Optional: role_id, is_active.

_No parameters._

---

#### `npg_set_user_password`

Set/reset a user's password. Required: user_id, new_password.

_No parameters._

---

#### `npg_assign_user_role`

Assign a role to a user. Required: user_id, role_id.

_No parameters._

---

#### `npg_end_user_sessions`

End all sessions for a user (force logout). Required: user_id.

_No parameters._

---

#### `npg_delete_user`

Delete a user by their ID.

_No parameters._

---

#### `npg_auth_change_username`

Change own username. REQUIRED: current_password, new_username.

_No parameters._

---

### SSO Providers (7)

#### `npg_list_sso_providers`

List all SSO providers.

_No parameters._

---

#### `npg_create_sso_provider`

Create a new SSO provider. Required: slug, name, issuer_url, client_id. Optional: client_secret (defaults to placeholder), scopes.

_No parameters._

---

#### `npg_update_sso_provider`

Update an SSO provider. Pass only fields to change. Required: provider_id. Optional: name, slug, issuer_url, client_id, client_secret (send '********' to leave unchanged), scopes.

_No parameters._

---

#### `npg_delete_sso_provider`

Delete an SSO provider by its ID.

_No parameters._

---

#### `npg_test_sso_provider`

Test SSO provider configuration by initiating a test login flow.

_No parameters._

---

#### `npg_get_auth_sso_providers`

List SSO providers available for the login screen (public-facing).

_No parameters._

---

#### `npg_auth_sso_start`

Begin an SSO login flow. REQUIRED: slug (the SSO provider identifier). Returns a redirect URL.

_No parameters._

---

### Other (6)

#### `npg_regenerate_config`

Regenerate nginx config for a specific proxy host without touching others.

_No parameters._

---

#### `npg_list_countries`

List available country codes for GeoIP blocking.

_No parameters._

---

#### `npg_detect_telegram_chats`

Detect available Telegram chats for notification delivery.

_No parameters._

---

#### `npg_import_from_hosts`

Import certificates from existing hosts.

_No parameters._

---

#### `npg_test_acme`

Test ACME configuration for DNS provider.

_No parameters._

---

#### `npg_get_global_rate_limit`

GET global rate limit configuration.

_No parameters._

---

### Dashboard (6)

#### `npg_get_dashboard`

Get dashboard data (summary of proxy hosts, certificates, etc.).

_No parameters._

---

#### `npg_get_dashboard_health`

Get system health status.

_No parameters._

---

#### `npg_get_dashboard_geoip_stats`

GET GeoIP statistics by country for the dashboard.

_No parameters._

---

#### `npg_get_dashboard_containers`

Get Docker container statistics for the dashboard.

_No parameters._

---

#### `npg_get_dashboard_stats`

Get hourly statistics for the dashboard.

_No parameters._

---

#### `npg_get_dashboard_health_history`

Get system health history for the dashboard.

_No parameters._

---

### IP Management (6)

#### `npg_ban_ip`

Ban an IP address. Required: ip. Optional: ban_time (seconds).

_No parameters._

---

#### `npg_unban_ip`

Unban an IP by its ID.

_No parameters._

---

#### `npg_bulk_unban_ips`

Unban multiple banned-IP records at once. REQUIRED: ids (list of record IDs).

_No parameters._

---

#### `npg_get_ban_history`

Get ban/unban event history.

_No parameters._

---

#### `npg_get_ban_history_stats`

Get ban/unban history statistics.

_No parameters._

---

#### `npg_get_ban_history_for_ip`

Get ban history for a specific IP address. REQUIRED: ip.

_No parameters._

---

### Notification Channels (6)

#### `npg_list_notification_channels`

List all notification channels.

_No parameters._

---

#### `npg_create_notification_channel`

Create a notification channel. Required: name, type (e.g. 'email', 'telegram', 'slack'). Optional: config (dict).

_No parameters._

---

#### `npg_update_notification_channel`

Update a notification channel. Pass only fields to change.

_No parameters._

---

#### `npg_delete_notification_channel`

Delete a notification channel by its ID.

_No parameters._

---

#### `npg_test_notification_channel`

Test a notification channel by sending a test message.

_No parameters._

---

#### `npg_get_notification_deliveries`

Get delivery history for a notification channel.

_No parameters._

---

### Redirect Hosts (5)

#### `npg_list_redirect_hosts`

List all redirect hosts.

_No parameters._

---

#### `npg_get_redirect_host`

Get a redirect host by its ID.

_No parameters._

---

#### `npg_create_redirect_host`

Create a new redirect host. Required: domain_names (list[str]), forward_domain_name (str). Optional: forward_scheme (auto/http/https, default auto), preserve_path (bool, default True), redirect_code (int, default 301).

_No parameters._

---

#### `npg_update_redirect_host`

Update a redirect host. Pass only fields to change. Fields: domain_names, forward_domain_name, forward_scheme, preserve_path, redirect_code.

_No parameters._

---

#### `npg_delete_redirect_host`

Delete a redirect host by its ID.

_No parameters._

---

### Access Lists (5)

#### `npg_list_access_lists`

List all access lists (authentication/restriction lists).

_No parameters._

---

#### `npg_get_access_list`

Get an access list by its ID.

_No parameters._

---

#### `npg_create_access_list`

Create a new access list. Required: name, advanced_config (block/allow rules).

_No parameters._

---

#### `npg_update_access_list`

Update an access list. Pass only fields to change.

_No parameters._

---

#### `npg_delete_access_list`

Delete an access list by its ID.

_No parameters._

---

### Geo (5)

#### `npg_get_geoip_status`

Get GeoIP database update status.

_No parameters._

---

#### `npg_update_geoip`

Update GeoIP databases.

_No parameters._

---

#### `npg_get_global_geo`

GET global GeoIP restriction configuration.

_No parameters._

---

#### `npg_update_global_geo`

UPDATE global GeoIP restriction configuration (partial update — only provided fields are changed; omitted fields are left as-is. The global default is inherited by hosts without their own override). Body: enabled (bool), mode (whitelist/blacklist), countries (list of ISO codes), allowed_ips, allow_private_ips, allow_search_bots, challenge_mode

_No parameters._

---

#### `npg_get_geoip_history`

List GeoIP database update runs and their status.

_No parameters._

---

### Fail2ban & Challenge (4)

#### `npg_verify_challenge`

Verify a CAPTCHA solution. Public endpoint. REQUIRED: token, solution.

_No parameters._

---

#### `npg_get_challenge_config`

GET the global CAPTCHA challenge configuration.

_No parameters._

---

#### `npg_update_challenge_config`

UPDATE the global CAPTCHA challenge configuration (partial update). Pass only fields to change.

_No parameters._

---

#### `npg_get_challenge_stats`

GET CAPTCHA challenge statistics.

_No parameters._

---

### Banned IPs & Bots (4)

#### `npg_list_banned_ips`

List banned IP addresses.

_No parameters._

---

#### `npg_get_bots_known`

Get list of known bot user-agent signatures.

_No parameters._

---

#### `npg_get_global_bot_filter`

GET global bot filter configuration.

_No parameters._

---

#### `npg_update_global_bot_filter`

UPDATE global bot filter configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, block_bad_bots, block_ai_bots, allow_search_engines, block_suspicious_clients, challenge_suspicious, custom_blocked_agents, custom_allowed_agents.

_No parameters._

---

### Roles (4)

#### `npg_list_roles`

List all roles.

_No parameters._

---

#### `npg_create_role`

Create a new role. Required: name, permissions (array of permission strings).

_No parameters._

---

#### `npg_update_role`

Update a role. Pass only fields to change.

_No parameters._

---

#### `npg_delete_role`

Delete a role by its ID.

_No parameters._

---

### System (4)

#### `npg_check_update`

Check for available NPG updates.

_No parameters._

---

#### `npg_update_global_rate_limit`

UPDATE global rate limit configuration (partial update — only provided fields are changed; omitted fields are left as-is). Body: enabled, requests_per_second, burst_size, zone_size, limit_by, limit_response.

_No parameters._

---

#### `npg_get_status`

Get component status — health of all NPG subsystems.

_No parameters._

---

#### `npg_check_npg_update`

Check for a newer NPG release version.

_No parameters._

---

### SSL / Nginx (3)

#### `npg_reload_nginx`

Reload nginx configuration without full restart.

_No parameters._

---

#### `npg_sync_nginx`

Sync all configs and reload nginx.

_No parameters._

---

#### `npg_test_nginx`

Test nginx configuration for validity.

_No parameters._

---

### System & Health (2)

#### `npg_get_upstream_health`

GET health status of an upstream pool. REQUIRED: upstream_id (UUID string).

_No parameters._

---

#### `npg_get_health_detailed`

Get a detailed health snapshot (detailed version of health check).

_No parameters._

---

### Docker (1)

#### `npg_get_docker_containers`

Get status of all Docker containers managed by NPG.

_No parameters._

---


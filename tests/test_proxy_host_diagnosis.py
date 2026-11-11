"""Unit tests for npg_get_proxy_host_diagnosis / _diagnose_proxy_host_sections.

Two layers are covered, both without network access:

* the **pure** check function — synthetic section payloads (shaped after the
  real NPG 2.69.0 responses) in, findings out: one test per check, plus the
  anti-false-positive contract (absent keys / failed sections never escalate
  to ``critical``) and the deterministic severity ordering;
* the **tool wrapper** — a recording fake client proves it issues only GETs
  (the read-tier contract), keeps ``sections_failed`` per section, and returns
  the documented envelope (counts, sections_checked, optional raw payloads).

The fixture payloads mirror what the isolated test stack actually returns for
``GET /api/v1/proxy-hosts/{id}`` and its per-host sub-resources, so a renamed
upstream field shows up here as a failing check rather than silently making the
tool report "no problems".
"""

from __future__ import annotations

import asyncio

import npg_mcp.main as main_mod

HOST_ID = "75a3ab6f-38b8-498a-b15a-6b18237e702a"


# ── Payload builders (real NPG 2.69.0 shapes) ──────────────────────────────
def _host(**overrides) -> dict:
    payload = {
        "id": HOST_ID,
        "proxy_type": "http",
        "domain_names": ["diag.example.test"],
        "forward_scheme": "http",
        "forward_host": "127.0.0.1",
        "forward_port": 8080,
        "ssl_enabled": True,
        "ssl_force_https": True,
        "waf_enabled": False,
        "waf_mode": "blocking",
        "waf_paranoia_level": 1,
        "waf_anomaly_threshold": 5,
        "waf_use_global": True,
        "enabled": True,
        "cache_enabled": False,
        "block_exploits": True,
        "config_status": "ok",
    }
    payload.update(overrides)
    return payload


def _challenge(**overrides) -> dict:
    payload = {
        "enabled": False,
        "challenge_type": "recaptcha_v2",
        "site_key": "",
        "has_secret_key": False,
        "token_validity": 86400,
        "min_score": 0.5,
        "apply_to": "both",
    }
    payload.update(overrides)
    return payload


def _geo(**overrides) -> dict:
    payload = {
        "enabled": False,
        "mode": "blacklist",
        "countries": [],
        "allowed_ips": [],
    }
    payload.update(overrides)
    return payload


def _uri_block(**overrides) -> dict:
    payload = {"enabled": False, "rules": [], "exception_ips": []}
    payload.update(overrides)
    return payload


def _rate_limit(**overrides) -> dict:
    payload = {
        "enabled": False,
        "requests_per_second": 10,
        "burst_size": 20,
        "disable_global": False,
    }
    payload.update(overrides)
    return payload


def _bot_filter(**overrides) -> dict:
    payload = {
        "enabled": False,
        "block_bad_bots": True,
        "block_ai_bots": False,
        "allow_search_engines": True,
        "block_suspicious_clients": False,
        "challenge_suspicious": False,
        "disable_global": False,
    }
    payload.update(overrides)
    return payload


def _fail2ban(**overrides) -> dict:
    payload = {
        "enabled": False,
        "max_retries": 5,
        "find_time": 600,
        "ban_time": 3600,
        "fail_codes": "401,403",
        "action": "block",
    }
    payload.update(overrides)
    return payload


def _waf(**overrides) -> dict:
    payload = {
        "proxy_host_id": HOST_ID,
        "waf_enabled": False,
        "waf_mode": "blocking",
        "exclusions": None,
        "exclusion_count": 0,
    }
    payload.update(overrides)
    return payload


def _sections(**overrides) -> dict:
    """A full default-config host: exactly what a fresh host looks like."""
    payloads = {
        "host": _host(),
        "rate_limit": _rate_limit(),
        "bot_filter": _bot_filter(),
        "security_headers": {"enabled": False, "hsts_enabled": True},
        "upstream": {"servers": [], "load_balance": "round_robin"},
        "geo": _geo(),
        "challenge": _challenge(),
        "fail2ban": _fail2ban(),
        "cloud_blocking": {"blocked_providers": [], "challenge_mode": False},
        "waf": _waf(),
        "uri_block": _uri_block(),
    }
    payloads.update(overrides)
    return payloads


def _checks(findings, severity=None) -> set[str]:
    return {
        f["check"] for f in findings if severity is None or f["severity"] == severity
    }


def _by_check(findings, check) -> dict:
    matches = [f for f in findings if f["check"] == check]
    assert len(matches) == 1, f"expected exactly one {check} finding, got {matches}"
    return matches[0]


class _RecordingClient:
    """Fake NPGClient: records every call, answers with per-path fixtures."""

    def __init__(self, responses: dict | None = None, failing: tuple[str, ...] = ()):
        self.calls: list[tuple[str, str]] = []
        self.responses = responses or {}
        self.failing = failing

    def get(self, path, params=None):
        self.calls.append(("GET", path))
        for suffix in self.failing:
            if path.endswith(suffix):
                raise RuntimeError("NPG API returned HTTP 500")
        for suffix, payload in self.responses.items():
            if path.endswith(suffix):
                return payload
        return {"path": path}

    def post(self, path, body=None):  # pragma: no cover - must never be called
        raise AssertionError(f"diagnosis tool issued a POST: {path}")

    def put(self, path, body=None, params=None):  # pragma: no cover
        raise AssertionError(f"diagnosis tool issued a PUT: {path}")

    def delete(self, path):  # pragma: no cover
        raise AssertionError(f"diagnosis tool issued a DELETE: {path}")


def _run(coro):
    return asyncio.run(coro)


# ── Clean host ─────────────────────────────────────────────────────────────
class TestCleanHost:
    def test_default_host_yields_no_findings(self):
        assert main_mod._diagnose_proxy_host_sections(_sections()) == []

    def test_missing_everything_yields_no_findings(self):
        # No key at all → every check is skipped; nothing is fabricated and
        # nothing is escalated to critical.
        assert main_mod._diagnose_proxy_host_sections({}) == []

    def test_non_dict_payloads_are_ignored(self):
        sections = {name: None for name in main_mod._PROXY_HOST_SECTION_NAMES}
        assert main_mod._diagnose_proxy_host_sections(sections, ["geo"]) != []
        assert _checks(main_mod._diagnose_proxy_host_sections(sections, ["geo"])) == {
            "section_unavailable"
        }

    def test_empty_dict_payloads_produce_nothing(self):
        sections = {name: {} for name in main_mod._PROXY_HOST_SECTION_NAMES}
        assert main_mod._diagnose_proxy_host_sections(sections) == []


# ── Host-level checks ──────────────────────────────────────────────────────
class TestHostChecks:
    def test_disabled_host_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(host=_host(enabled=False))
        )
        finding = _by_check(findings, "host_disabled")
        assert finding["severity"] == "warning"
        assert finding["section"] == "host"

    def test_absent_enabled_key_is_not_a_finding(self):
        host = _host()
        del host["enabled"]
        assert main_mod._diagnose_proxy_host_sections(_sections(host=host)) == []

    def test_tls_with_empty_certificate_is_critical(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(host=_host(ssl_enabled=True, certificate_id=None))
        )
        finding = _by_check(findings, "tls_without_certificate")
        assert finding["severity"] == "critical"
        assert finding["section"] == "host"

    def test_tls_with_certificate_is_clean(self):
        host = _host(
            ssl_enabled=True, certificate_id="615aabe5-c513-4db5-9196-c24b604716b2"
        )
        assert main_mod._diagnose_proxy_host_sections(_sections(host=host)) == []

    def test_absent_certificate_key_never_escalates(self):
        """The API omits certificate_id when a default cert is auto-assigned."""
        findings = main_mod._diagnose_proxy_host_sections(_sections(host=_host()))
        assert "tls_without_certificate" not in _checks(findings)
        assert "critical" not in {f["severity"] for f in findings}

    def test_zero_forward_port_is_critical(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(host=_host(forward_port=0))
        )
        assert _by_check(findings, "no_upstream_target")["severity"] == "critical"

    def test_empty_forward_host_is_critical(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(host=_host(forward_host="   "))
        )
        assert _by_check(findings, "no_upstream_target")["severity"] == "critical"

    def test_stream_host_without_forward_fields_is_clean(self):
        host = _host(
            proxy_type="stream",
            forward_host="",
            forward_port=0,
        )
        findings = main_mod._diagnose_proxy_host_sections(_sections(host=host))
        assert "no_upstream_target" not in _checks(findings)

    def test_waf_use_global_true_with_tuned_host_waf_is_info(self):
        host = _host(waf_use_global=True, waf_paranoia_level=2)
        findings = main_mod._diagnose_proxy_host_sections(_sections(host=host))
        finding = _by_check(findings, "waf_use_global_ignores_host_waf")
        assert finding["severity"] == "info"
        assert "waf_paranoia_level" in finding["detail"]

    def test_waf_use_global_true_with_default_host_waf_is_silent(self):
        """Untouched create defaults are not evidence the caller tuned the WAF."""
        host = _host(
            waf_use_global=True,
            waf_enabled=False,
            waf_mode="blocking",
            waf_paranoia_level=1,
            waf_anomaly_threshold=5,
        )
        findings = main_mod._diagnose_proxy_host_sections(_sections(host=host))
        assert "waf_use_global_ignores_host_waf" not in _checks(findings)

    def test_waf_use_global_false_never_warns_about_ignored_fields(self):
        host = _host(waf_use_global=False, waf_paranoia_level=3, waf_enabled=True)
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(host=host, waf=_waf(waf_enabled=True))
        )
        assert "waf_use_global_ignores_host_waf" not in _checks(findings)


# ── Challenge ──────────────────────────────────────────────────────────────
class TestChallengeChecks:
    def test_enabled_without_secret_key_is_critical(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                challenge=_challenge(
                    enabled=True,
                    site_key="1x00000000000000000000AA",
                    has_secret_key=False,
                )
            )
        )
        finding = _by_check(findings, "challenge_keys_incomplete")
        assert finding["severity"] == "critical"
        assert finding["section"] == "challenge"
        assert "secret_key missing" in finding["detail"]

    def test_enabled_without_site_key_is_critical(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                challenge=_challenge(enabled=True, site_key="", has_secret_key=True)
            )
        )
        finding = _by_check(findings, "challenge_keys_incomplete")
        assert finding["severity"] == "critical"
        assert "site_key empty" in finding["detail"]

    def test_enabled_with_both_keys_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                challenge=_challenge(
                    enabled=True,
                    site_key="1x00000000000000000000AA",
                    has_secret_key=True,
                )
            )
        )
        assert findings == []

    def test_enabled_with_blank_challenge_type_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                challenge=_challenge(
                    enabled=True,
                    challenge_type="",
                    site_key="1x00000000000000000000AA",
                    has_secret_key=True,
                )
            )
        )
        assert _by_check(findings, "challenge_type_missing")["severity"] == "warning"

    def test_disabled_challenge_is_never_diagnosed(self):
        # has_secret_key false / site_key empty are the create defaults; a
        # disabled challenge must not be reported.
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                challenge=_challenge(enabled=False, site_key="", has_secret_key=False)
            )
        )
        assert findings == []


# ── Geo ────────────────────────────────────────────────────────────────────
class TestGeoCases:
    def test_whitelist_without_countries_is_critical(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(geo=_geo(enabled=True, mode="whitelist", countries=[]))
        )
        finding = _by_check(findings, "geo_whitelist_empty")
        assert finding["severity"] == "critical"
        assert finding["section"] == "geo"

    def test_blacklist_without_countries_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(geo=_geo(enabled=True, mode="blacklist", countries=[]))
        )
        assert _by_check(findings, "geo_blacklist_empty")["severity"] == "warning"

    def test_whitelist_with_countries_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(geo=_geo(enabled=True, mode="whitelist", countries=["KR", "US"]))
        )
        assert findings == []

    def test_disabled_geo_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(geo=_geo(enabled=False, mode="whitelist", countries=[]))
        )
        assert findings == []


# ── Enabled-but-empty sub-features ─────────────────────────────────────────
class TestEnabledButEmpty:
    def test_uri_block_without_rules_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(uri_block=_uri_block(enabled=True, rules=[]))
        )
        assert _by_check(findings, "uri_block_no_rules")["severity"] == "warning"

    def test_uri_block_with_rules_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                uri_block=_uri_block(enabled=True, rules=[{"pattern": "^/admin"}])
            )
        )
        assert findings == []

    def test_rate_limit_without_threshold_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(rate_limit=_rate_limit(enabled=True, requests_per_second=0))
        )
        assert _by_check(findings, "rate_limit_no_threshold")["severity"] == "warning"

    def test_rate_limit_with_threshold_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(rate_limit=_rate_limit(enabled=True, requests_per_second=10))
        )
        assert findings == []

    def test_bot_filter_with_every_mode_off_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                bot_filter=_bot_filter(
                    enabled=True,
                    block_bad_bots=False,
                    block_ai_bots=False,
                    block_suspicious_clients=False,
                    challenge_suspicious=False,
                )
            )
        )
        assert _by_check(findings, "bot_filter_no_mode")["severity"] == "warning"

    def test_bot_filter_with_one_mode_on_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(bot_filter=_bot_filter(enabled=True, block_bad_bots=True))
        )
        assert findings == []

    def test_fail2ban_with_empty_codes_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(fail2ban=_fail2ban(enabled=True, fail_codes=""))
        )
        assert _by_check(findings, "fail2ban_no_fail_codes")["severity"] == "warning"

    def test_fail2ban_with_empty_code_list_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(fail2ban=_fail2ban(enabled=True, fail_codes=[]))
        )
        assert _by_check(findings, "fail2ban_no_fail_codes")["severity"] == "warning"

    def test_fail2ban_with_codes_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(fail2ban=_fail2ban(enabled=True, fail_codes="401,403"))
        )
        assert findings == []


# ── WAF effective-config drift + failed sections ───────────────────────────
class TestDriftAndFailures:
    def test_stored_waf_enabled_but_effective_disabled_is_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                host=_host(waf_use_global=False, waf_enabled=True),
                waf=_waf(waf_enabled=False),
            )
        )
        finding = _by_check(findings, "waf_not_effective")
        assert finding["severity"] == "warning"
        assert finding["section"] == "waf"

    def test_matching_waf_state_is_clean(self):
        findings = main_mod._diagnose_proxy_host_sections(
            _sections(
                host=_host(waf_use_global=False, waf_enabled=True),
                waf=_waf(waf_enabled=True),
            )
        )
        assert findings == []

    def test_failed_section_is_reported_as_a_warning(self):
        findings = main_mod._diagnose_proxy_host_sections(_sections(), ["geo", "waf"])
        unavailable = [f for f in findings if f["check"] == "section_unavailable"]
        assert [f["section"] for f in unavailable] == ["geo", "waf"]
        assert {f["severity"] for f in unavailable} == {"warning"}
        assert "incomplete" in unavailable[0]["detail"]

    def test_failed_section_never_produces_a_critical(self):
        findings = main_mod._diagnose_proxy_host_sections(
            {}, ["host", "challenge", "geo"]
        )
        assert "critical" not in {f["severity"] for f in findings}


# ── Ordering + shape ───────────────────────────────────────────────────────
class TestFindingOrdering:
    def _messy(self) -> list[dict]:
        return main_mod._diagnose_proxy_host_sections(
            _sections(
                host=_host(
                    enabled=False,
                    ssl_enabled=True,
                    certificate_id=None,
                    waf_use_global=True,
                    waf_paranoia_level=4,
                ),
                challenge=_challenge(enabled=True, site_key="", has_secret_key=False),
                geo=_geo(enabled=True, mode="whitelist", countries=[]),
                uri_block=_uri_block(enabled=True, rules=[]),
            ),
            ["waf"],
        )

    def test_findings_are_sorted_by_severity_rank(self):
        order = {name: i for i, name in enumerate(main_mod._DIAG_SEVERITIES)}
        ranks = [order[f["severity"]] for f in self._messy()]
        assert ranks == sorted(ranks)

    def test_every_finding_has_the_documented_shape(self):
        for finding in self._messy():
            assert set(finding) == {"severity", "check", "section", "detail"}
            assert finding["severity"] in main_mod._DIAG_SEVERITIES
            assert isinstance(finding["detail"], str) and finding["detail"]
            assert isinstance(finding["section"], str) and finding["section"]

    def test_all_expected_checks_fire_together(self):
        assert _checks(self._messy()) == {
            "tls_without_certificate",
            "geo_whitelist_empty",
            "challenge_keys_incomplete",
            "host_disabled",
            "uri_block_no_rules",
            "waf_use_global_ignores_host_waf",
            "section_unavailable",
        }

    def test_output_is_deterministic(self):
        first = self._messy()
        second = main_mod._diagnose_proxy_host_sections(
            _sections(
                host=_host(
                    enabled=False,
                    ssl_enabled=True,
                    certificate_id=None,
                    waf_use_global=True,
                    waf_paranoia_level=4,
                ),
                challenge=_challenge(enabled=True, site_key="", has_secret_key=False),
                geo=_geo(enabled=True, mode="whitelist", countries=[]),
                uri_block=_uri_block(enabled=True, rules=[]),
            ),
            ["waf"],
        )
        assert first == second


# ── Tool wrapper ───────────────────────────────────────────────────────────
class TestDiagnosisTool:
    def _client(self, monkeypatch, **kwargs) -> _RecordingClient:
        client = _RecordingClient(**kwargs)
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        return client

    def test_issues_only_gets_over_the_same_section_paths(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(main_mod.npg_get_proxy_host_diagnosis(HOST_ID))
        assert result["success"] is True
        assert len(client.calls) == 11
        assert {method for method, _ in client.calls} == {"GET"}
        assert ("GET", f"/api/v1/waf/hosts/{HOST_ID}/config") in client.calls
        assert ("GET", f"/api/v1/proxy-hosts/{HOST_ID}") in client.calls
        assert result["data"]["sections_checked"] == list(
            main_mod._PROXY_HOST_SECTION_NAMES
        )
        assert result["data"]["sections_failed"] == []

    def test_envelope_shape_and_counts(self, monkeypatch):
        self._client(
            monkeypatch,
            responses={
                f"/proxy-hosts/{HOST_ID}": _host(enabled=False),
                "/challenge": _challenge(
                    enabled=True, site_key="", has_secret_key=False
                ),
            },
        )
        result = _run(main_mod.npg_get_proxy_host_diagnosis(HOST_ID))
        data = result["data"]
        assert data["host_id"] == HOST_ID
        assert data["domain_names"] == ["diag.example.test"]
        assert data["counts"] == {"critical": 1, "warning": 1, "info": 0}
        assert [f["check"] for f in data["findings"]] == [
            "challenge_keys_incomplete",
            "host_disabled",
        ]

    def test_failed_section_keeps_the_call_successful(self, monkeypatch):
        self._client(monkeypatch, failing=("/geo",))
        result = _run(main_mod.npg_get_proxy_host_diagnosis(HOST_ID))
        assert result["success"] is True
        assert result["data"]["sections_failed"] == ["geo"]
        assert "geo" not in result["data"]["sections_checked"]
        assert _checks(result["data"]["findings"]) == {"section_unavailable"}

    def test_sections_subset_limits_the_fetches(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(
            main_mod.npg_get_proxy_host_diagnosis(
                HOST_ID, sections=["geo", "challenge"]
            )
        )
        assert len(client.calls) == 2
        assert result["data"]["sections_checked"] == ["geo", "challenge"]
        assert result["data"]["domain_names"] == []

    def test_invalid_section_is_rejected_before_any_request(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(
            main_mod.npg_get_proxy_host_diagnosis(HOST_ID, sections=["bogus"])
        )
        assert result["success"] is False
        assert "bogus" in result["error"]
        assert client.calls == []

    def test_expand_declares_the_cap_contract_without_changing_the_payload(
        self, monkeypatch
    ):
        """``expand`` is the shared read-tool cap switch, not a payload switch.

        ``resultcap.instrument_tools`` consumes ``expand`` before the tool body
        runs, so the body must never rely on it — and the raw section payloads
        deliberately stay out of the response (``npg_get_proxy_host_full`` is
        the raw view).
        """
        self._client(monkeypatch, responses={f"/proxy-hosts/{HOST_ID}": _host()})
        compact = _run(main_mod.npg_get_proxy_host_diagnosis(HOST_ID))
        expanded = _run(main_mod.npg_get_proxy_host_diagnosis(HOST_ID, expand=True))
        assert expanded == compact
        assert "raw" not in compact["data"]
        assert set(compact["data"]) == {
            "host_id",
            "domain_names",
            "findings",
            "counts",
            "sections_checked",
            "sections_failed",
        }

    def test_invalid_host_id_is_rejected(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(main_mod.npg_get_proxy_host_diagnosis(""))
        assert result["success"] is False
        assert result["error"]
        assert client.calls == []

    def test_int_id_is_interpolated_as_a_plain_path_segment(self, monkeypatch):
        client = self._client(monkeypatch)
        result = _run(main_mod.npg_get_proxy_host_diagnosis(42, sections=["host"]))
        assert result["success"] is True
        assert client.calls == [("GET", "/api/v1/proxy-hosts/42")]
        assert result["data"]["host_id"] == "42"

    def test_tool_is_registered_and_read_only(self):
        import npg_mcp.toolsets as toolsets

        names = toolsets._discover_tool_names()
        assert "npg_get_proxy_host_diagnosis" in names
        assert "npg_get_proxy_host_diagnosis" in toolsets.tier_allowed(names, "read")
        annotations = toolsets.annotations_for("npg_get_proxy_host_diagnosis")
        assert annotations is not None
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False

    def test_description_stays_within_the_desc_len_gate(self):
        tool = next(
            t
            for t in main_mod.mcp._tool_manager.list_tools()
            if t.name == "npg_get_proxy_host_diagnosis"
        )
        assert len(tool.description or "") <= 460

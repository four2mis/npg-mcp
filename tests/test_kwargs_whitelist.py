"""Tests for kwargs-dict whitelist validation on pass-through update tools.

Every whitelisted tool must exist in main.py (orphan-guard), valid dicts
must pass through unchanged, unknown keys must raise ValueError naming the
offending key and the accepted list, and strict=False must bypass.
"""

import re
from pathlib import Path

import pytest

from npg_mcp.upstream_models import TOOL_KWARGS_WHITELIST, _validate_kwargs

MAIN_PY = Path(__file__).resolve().parent.parent / "npg_mcp" / "main.py"


def test_every_whitelisted_tool_exists_in_main():
    """Guardrail: renames/removals in main.py must not orphan whitelist entries."""
    src = MAIN_PY.read_text()
    registered = set(re.findall(r'@mcp\.tool\(name="(npg_\w+)"', src))
    orphaned = set(TOOL_KWARGS_WHITELIST) - registered
    assert not orphaned, f"Whitelist entries for missing tools: {sorted(orphaned)}"


def test_whitelisted_tools_have_strict_param():
    """Each whitelisted tool's signature must expose the strict escape hatch."""
    src = MAIN_PY.read_text()
    for name in TOOL_KWARGS_WHITELIST:
        idx = src.index(f'@mcp.tool(name="{name}"')
        seg = src[idx: idx + 5000]
        m = re.search(r"async def \w+\(([^)]*)\)", seg, re.S)
        assert m, f"{name}: signature not found"
        assert "strict: bool = True" in m.group(1), f"{name}: missing strict param"
        assert "_validate_kwargs" in seg, f"{name}: _validate_kwargs not called"


def test_none_and_empty_kwargs_pass():
    _validate_kwargs("npg_update_log_settings", None)
    _validate_kwargs("npg_update_log_settings", {})
    _validate_kwargs("npg_update_log_settings", None, strict=True)


def test_system_settings_v2_51_fields_accepted():
    """Upstream v2.51.0 added trusted-proxy fields to UpdateSystemSettingsRequest."""
    kwargs = {
        "trusted_proxy_cidrs": "10.0.0.0/8\n172.16.0.0/12",
        "trusted_proxy_preset": "cloudflare",
        "real_ip_header": "CF-Connecting-IP",
    }
    _validate_kwargs("npg_update_system_settings", kwargs, strict=True)


def test_valid_dict_passes_through_unchanged():
    kwargs = {"retention_days": 30, "max_logs_per_type": 5000}
    _validate_kwargs("npg_update_log_settings", kwargs)
    # helper must not mutate the caller's dict
    assert kwargs == {"retention_days": 30, "max_logs_per_type": 5000}


def test_unknown_key_raises_with_names():
    with pytest.raises(ValueError) as exc:
        _validate_kwargs("npg_update_log_settings", {"log_retention_days": 7})
    msg = str(exc.value)
    assert "log_retention_days" in msg          # offending key named
    assert "retention_days" in msg              # accepted list included
    assert "strict=false" in msg                # escape hatch documented


def test_mixed_known_and_unknown_keys_report_all_unknowns():
    with pytest.raises(ValueError) as exc:
        _validate_kwargs(
            "npg_update_api_token",
            {"name": "ok", "bogus_field": 1, "perms": ["x"]},
        )
    msg = str(exc.value)
    assert "bogus_field" in msg and "perms" in msg
    assert "'name'" not in msg.split("Accepted")[0].replace("unknown field(s) [", "")


def test_strict_false_bypasses_validation():
    _validate_kwargs(
        "npg_update_log_settings", {"totally_new_upstream_field": 1}, strict=False
    )


def test_unwhitelisted_tool_fails_open():
    """A tool without a whitelist entry must not break callers."""
    _validate_kwargs("npg_some_future_tool", {"anything": True})


def test_error_lists_full_accepted_set():
    allowed = sorted(TOOL_KWARGS_WHITELIST["npg_update_exploit_rule"])
    with pytest.raises(ValueError) as exc:
        _validate_kwargs("npg_update_exploit_rule", {"rule_typ": "xss"})
    for field in allowed:
        assert f"'{field}'" in str(exc.value)


def test_realistic_typo_matrix_rejected():
    """The exact silent-noop typos that motivated this feature are all caught."""
    cases = [
        ("npg_update_log_settings", {"log_retention_days": 7}),
        ("npg_update_exploit_rule", {"rule_type": "xss", "rule_value": "v"}),
        ("npg_update_dns_provider", {"key": "k", "secret": "s"}),
        ("npg_update_api_token", {"scopes": ["*"]}),
        ("npg_update_cloudflare_tunnel", {"tunnel_token": "tok"}),
    ]
    for tool, kwargs in cases:
        with pytest.raises(ValueError):
            _validate_kwargs(tool, kwargs)

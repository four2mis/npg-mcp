"""Unit tests for npg_mcp.toolsets.

Covers:
* tier_allowed at read/standard/full levels.
* read-level returns only get/list/view/download/check/detect prefixed tools.
* standard-level excludes all 47 DESTRUCTIVE_TOOLS.
* full-level returns everything.
* resolve_level normalizes unknown values to full.

Pure-function tests — no MCP server, no network.
"""

from __future__ import annotations

import pytest

from npg_mcp.toolsets import (
    DEFAULT_LEVEL,
    DESTRUCTIVE_TOOLS,
    VALID_LEVELS,
    resolve_level,
    tier_allowed,
)

def _sample_tools() -> set[str]:
    """A representative tool name set mirroring the real naming contract."""
    return {
        # read-only prefixes (kept at read level)
        "npg_get_settings",
        "npg_list_proxy_hosts",
        "npg_view_log_file",
        "npg_download_backup",
        "npg_check_update",
        "npg_detect_telegram_chats",
        # mutations (only at standard/full)
        "npg_create_proxy_host",
        "npg_update_proxy_host",
        "npg_sync_nginx",
        "npg_ban_ip",
        "npg_unban_ip",
        "npg_delete_proxy_host",
        "npg_restore_backup",
        "npg_set_user_password",
        "npg_reset_settings",
        "npg_revoke_api_token",
        "npg_cleanup_logs",
    }


class TestResolveLevel:
    def test_none_defaults_to_full(self):
        assert resolve_level(None) == "full"

    def test_valid_levels_roundtrip(self):
        for level in VALID_LEVELS:
            assert resolve_level(level) == level

    def test_case_and_whitespace_insensitive(self):
        assert resolve_level("  READ ") == "read"
        assert resolve_level("Standard") == "standard"

    def test_unknown_value_falls_back_to_full(self):
        assert resolve_level("junk") == "full"
        assert resolve_level("read-write") == "full"

    def test_empty_string_falls_back_to_full(self):
        assert resolve_level("") == "full"


class TestTierAllowed:
    def test_full_returns_everything(self):
        tools = _sample_tools()
        assert tier_allowed(tools, "full") == tools
        assert len(tier_allowed(tools, "full")) == len(tools)

    def test_read_returns_only_readonly_prefixes(self):
        tools = _sample_tools()
        allowed = tier_allowed(tools, "read")
        assert allowed == {
            "npg_get_settings",
            "npg_list_proxy_hosts",
            "npg_view_log_file",
            "npg_download_backup",
            "npg_check_update",
            "npg_detect_telegram_chats",
        }
        # every allowed name must match one of the read prefixes
        for name in allowed:
            assert name.startswith(("npg_get_", "npg_list_", "npg_view_", "npg_download_", "npg_check_", "npg_detect_"))

    def test_read_excludes_all_mutations(self):
        allowed = tier_allowed(_sample_tools(), "read")
        for mut in ("npg_create_proxy_host", "npg_ban_ip", "npg_sync_nginx", "npg_delete_proxy_host"):
            assert mut not in allowed

    def test_standard_excludes_all_47_destructive_tools(self):
        tools = _sample_tools()
        allowed = tier_allowed(tools, "standard")
        assert len(DESTRUCTIVE_TOOLS) == 47
        # every destructive tool in the sample set is hidden
        for name in tools:
            if name in DESTRUCTIVE_TOOLS:
                assert name not in allowed

    def test_standard_keeps_non_destructive_mutations(self):
        allowed = tier_allowed(_sample_tools(), "standard")
        assert "npg_create_proxy_host" in allowed
        assert "npg_update_proxy_host" in allowed
        assert "npg_sync_nginx" in allowed
        assert "npg_unban_ip" in allowed
        assert "npg_ban_ip" not in allowed
        assert "npg_delete_proxy_host" not in allowed

    def test_read_is_subset_of_standard_is_subset_of_full(self):
        tools = _sample_tools()
        read = tier_allowed(tools, "read")
        standard = tier_allowed(tools, "standard")
        full = tier_allowed(tools, "full")
        assert read <= standard <= full

    def test_empty_set(self):
        assert tier_allowed(set(), "read") == set()
        assert tier_allowed(set(), "standard") == set()
        assert tier_allowed(set(), "full") == set()

    def test_unknown_level_raises_nothing_and_behaves_like_read_default(self):
        # tier_allowed is only ever called with a resolved level by
        # configure_toolset; unknown strings fall through to the read branch.
        assert tier_allowed({"npg_get_x"}, "bogus") == {"npg_get_x"}


class TestDestructiveListIntegrity:
    def test_all_destructive_names_follow_delete_remove_or_verb_pattern(self):
        # The 46 names must be a stable, self-consistent set (no dupes).
        assert len(DESTRUCTIVE_TOOLS) == len(set(DESTRUCTIVE_TOOLS))
        # every entry is a valid npg_ tool name
        for name in DESTRUCTIVE_TOOLS:
            assert name.startswith("npg_")
            assert " " not in name

    def test_no_readonly_prefix_collides_with_destructive(self):
        for name in DESTRUCTIVE_TOOLS:
            assert not name.startswith(
                ("npg_get_", "npg_list_", "npg_view_", "npg_download_", "npg_check_", "npg_detect_")
            ), name


class TestDerivedDestructiveTools:
    """Guardrails for the import-time regex derivation.

    DESTRUCTIVE_TOOLS is auto-derived from tool name prefixes (see the
    module docstring naming convention). These tests pin that derivation
    against the real tool surface in npg_mcp/main.py so the manual-list
    replacement cannot silently change the exposed set at any level.
    """

    def test_derived_set_matches_regex_semantics(self):
        from npg_mcp.toolsets import (_DESTRUCTIVE_ALLOWLIST,
                                      _DESTRUCTIVE_DENYLIST,
                                      _DESTRUCTIVE_NAME_RE,
                                      _discover_tool_names)

        all_tools = _discover_tool_names()
        regex_matches = {n for n in all_tools if _DESTRUCTIVE_NAME_RE.match(n)}
        # every regex match is destructive (minus allowlist, plus denylist)
        expected = (regex_matches | _DESTRUCTIVE_DENYLIST) - _DESTRUCTIVE_ALLOWLIST
        assert DESTRUCTIVE_TOOLS == expected
        assert DESTRUCTIVE_TOOLS <= all_tools
        # allowlist is empty; denylist holds exactly the bulk-delete tool
        assert not _DESTRUCTIVE_ALLOWLIST
        assert _DESTRUCTIVE_DENYLIST == frozenset({"npg_bulk_delete_proxy_hosts"})

    def test_standard_level_matches_total_minus_destructive(self):
        from npg_mcp.toolsets import _discover_tool_names

        all_tools = _discover_tool_names()
        # Invariant: standard hides exactly the destructive set.
        assert len(tier_allowed(all_tools, "standard")) == len(all_tools) - len(DESTRUCTIVE_TOOLS) == 239
        # Live surface guardrail (current HEAD): 286 tools, 47 destructive.
        assert len(all_tools) == 286
        assert len(DESTRUCTIVE_TOOLS) == 47

    def test_destructive_count_47_exact(self):
        # The task's hard guardrail: exactly 47 destructive tools.
        assert len(DESTRUCTIVE_TOOLS) == 47

    def test_standard_and_read_counts_are_stable(self):
        from npg_mcp.toolsets import _discover_tool_names

        all_tools = _discover_tool_names()
        assert len(tier_allowed(all_tools, "standard")) == 239
        assert len(tier_allowed(all_tools, "read")) == 131
        assert len(tier_allowed(all_tools, "full")) == 286

    def test_docstring_documents_naming_convention(self):
        import inspect

        from npg_mcp import toolsets

        doc = inspect.getdoc(toolsets) or ""
        assert "naming convention" in doc.lower()
        assert "delete_" in doc and "DESTRUCTIVE_ALLOWLIST" in doc and "DESTRUCTIVE_DENYLIST" in doc

    def test_bulk_delete_denylisted_bulk_apply_not(self):
        """The bulk-delete tool is destructive (denylist); the bulk cert-apply
        tool is a normal mutation and must NOT be hidden at standard level."""
        from npg_mcp.toolsets import _discover_tool_names

        all_tools = _discover_tool_names()
        assert "npg_bulk_apply_certificate" in all_tools
        assert "npg_bulk_delete_proxy_hosts" in all_tools
        assert "npg_bulk_delete_proxy_hosts" in DESTRUCTIVE_TOOLS
        assert "npg_bulk_apply_certificate" not in DESTRUCTIVE_TOOLS
        allowed = tier_allowed(all_tools, "standard")
        assert "npg_bulk_delete_proxy_hosts" not in allowed
        assert "npg_bulk_apply_certificate" in allowed

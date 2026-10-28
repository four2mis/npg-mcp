"""Unit tests for npg_mcp.toolsets.

Covers:
* tier_allowed at read/standard/full levels.
* read-level returns only get/list/view/download/check/detect prefixed tools.
* standard-level excludes all 47 DESTRUCTIVE_TOOLS.
* full-level returns everything.
* resolve_level normalizes unknown values to full.
* MCP ToolAnnotations: every tool annotated, destructive/read-only/idempotent/
  open-world hints derived from each tool's HTTP verbs, hints reaching the
  served tools/list surface.

Pure-function tests — no MCP server, no network.
"""

from __future__ import annotations

from npg_mcp.toolsets import (
    DESTRUCTIVE_TOOLS,
    VALID_LEVELS,
    annotate_tools,
    annotations_for,
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
            assert name.startswith(
                ("npg_get_", "npg_list_", "npg_view_",
                 "npg_download_", "npg_check_", "npg_detect_")
            )

    def test_read_excludes_all_mutations(self):
        allowed = tier_allowed(_sample_tools(), "read")
        for mut in (
            "npg_create_proxy_host",
            "npg_ban_ip",
            "npg_delete_proxy_host",
        ):
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
                ("npg_get_", "npg_list_", "npg_view_", "npg_download_",
                 "npg_check_", "npg_detect_")
            ), name


class TestDerivedDestructiveTools:
    """Guardrails for the import-time regex derivation.

    DESTRUCTIVE_TOOLS is auto-derived from tool name prefixes (see the
    module docstring naming convention). These tests pin that derivation
    against the real tool surface in npg_mcp/main.py so the manual-list
    replacement cannot silently change the exposed set at any level.
    """

    def test_derived_set_matches_regex_semantics(self):
        from npg_mcp.toolsets import (
            _DESTRUCTIVE_ALLOWLIST,
            _DESTRUCTIVE_DENYLIST,
            _DESTRUCTIVE_NAME_RE,
            _discover_tool_names,
        )

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
        assert (
            len(tier_allowed(all_tools, "standard"))
            == len(all_tools) - len(DESTRUCTIVE_TOOLS)
            == 261
        )
        # Live surface guardrail (current HEAD): 308 tools, 47 destructive.
        assert len(all_tools) == 308
        assert len(DESTRUCTIVE_TOOLS) == 47

    def test_destructive_count_47_exact(self):
        # The task's hard guardrail: exactly 47 destructive tools.
        assert len(DESTRUCTIVE_TOOLS) == 47

    def test_standard_and_read_counts_are_stable(self):
        from npg_mcp.toolsets import _discover_tool_names

        all_tools = _discover_tool_names()
        assert len(tier_allowed(all_tools, "standard")) == 261
        assert len(tier_allowed(all_tools, "read")) == 139
        assert len(tier_allowed(all_tools, "full")) == 308

    def test_docstring_documents_naming_convention(self):
        import inspect

        from npg_mcp import toolsets

        doc = inspect.getdoc(toolsets) or ""
        assert "naming convention" in doc.lower()
        assert "delete_" in doc
        assert "DESTRUCTIVE_ALLOWLIST" in doc
        assert "DESTRUCTIVE_DENYLIST" in doc

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


def _hints(annotations) -> dict:
    """Return ToolAnnotations as protocol wire names (mcp 1.x and 2.x safe).

    mcp 1.x declares the fields camelCase (``readOnlyHint``); mcp 2.x renames
    them snake_case with camelCase aliases. ``model_dump(by_alias=True)`` yields
    the camelCase wire names on both, so the tests never depend on the installed
    SDK's Python attribute names.
    """
    return annotations.model_dump(by_alias=True)


class TestToolAnnotations:
    """MCP ToolAnnotations are derived per tool and reach the served surface.

    Classification is derived from the HTTP verbs each tool body calls
    (AST-harvested from ``npg_mcp/main.py``) plus the destructive-name registry
    — never from a hand-maintained name table — so these tests pin the
    derivation itself rather than a snapshot of its output.
    """

    @staticmethod
    def _served() -> dict:
        """``tools/list`` exactly as an MCP client receives it."""
        import asyncio

        import npg_mcp.main as main_mod

        annotate_tools(main_mod.mcp)
        return {tool.name: tool for tool in asyncio.run(main_mod.mcp.list_tools())}

    def test_every_registered_tool_is_annotated(self):
        from npg_mcp.toolsets import _discover_tool_names

        all_tools = _discover_tool_names()
        assert len(all_tools) == 308
        missing = sorted(n for n in all_tools if annotations_for(n) is None)
        assert missing == []

    def test_every_tool_body_yields_route_data(self):
        """A tool whose HTTP call convention is unrecognized fails here."""
        from npg_mcp.toolsets import _discover_tool_names, _tool_verbs

        verbs = _tool_verbs()
        assert set(verbs) == _discover_tool_names()
        assert sorted(n for n, v in verbs.items() if not v) == []

    def test_destructive_tools_carry_destructive_hint(self):
        assert DESTRUCTIVE_TOOLS
        for name in DESTRUCTIVE_TOOLS:
            hints = _hints(annotations_for(name))
            assert hints["destructiveHint"] is True, name
            assert hints["readOnlyHint"] is False, name
            assert hints["idempotentHint"] is False, name

    def test_get_only_tools_are_read_only(self):
        from npg_mcp.toolsets import _READ_VERBS, _READONLY_DENYLIST, _tool_verbs

        get_only = [
            name
            for name, verbs in _tool_verbs().items()
            if verbs and verbs <= _READ_VERBS and name not in _READONLY_DENYLIST
        ]
        assert len(get_only) > 100
        for name in get_only:
            assert _hints(annotations_for(name))["readOnlyHint"] is True, name

    def test_mutating_routes_are_never_read_only(self):
        from npg_mcp.toolsets import _MUTATING_VERBS, _tool_verbs

        mutating = [
            name
            for name, verbs in _tool_verbs().items()
            if verbs & _MUTATING_VERBS
        ]
        assert len(mutating) > 100
        for name in mutating:
            assert _hints(annotations_for(name))["readOnlyHint"] is False, name

    def test_idempotent_hint_rules(self):
        from npg_mcp.toolsets import _READ_VERBS, _tool_verbs

        for name, verbs in _tool_verbs().items():
            expected = (
                bool(verbs)
                and name not in DESTRUCTIVE_TOOLS
                and verbs <= (_READ_VERBS | {"put"})
            )
            hints = _hints(annotations_for(name))
            assert hints["idempotentHint"] is expected, name

    def test_readonly_denylist_entries_are_live_get_only_tools(self):
        """A stale denylist entry (or a newly side-effecting GET) fails here."""
        from npg_mcp.toolsets import _READ_VERBS, _READONLY_DENYLIST, _tool_verbs

        verbs = _tool_verbs()
        assert "npg_check_backup_restore" in _READONLY_DENYLIST
        for name in _READONLY_DENYLIST:
            assert name in verbs, f"stale denylist entry {name}"
            assert verbs[name] <= _READ_VERBS, f"{name} is not GET-only"
            assert _hints(annotations_for(name))["readOnlyHint"] is False

    def test_closed_world_tools_are_registered_read_only_catalogs(self):
        from npg_mcp.toolsets import _CLOSED_WORLD_TOOLS, _READ_VERBS, _tool_verbs

        verbs = _tool_verbs()
        assert _CLOSED_WORLD_TOOLS
        for name in _CLOSED_WORLD_TOOLS:
            assert name in verbs, f"unknown closed-world tool {name}"
            assert verbs[name] <= _READ_VERBS, name
            hints = _hints(annotations_for(name))
            assert hints["readOnlyHint"] is True, name
            assert hints["openWorldHint"] is False, name
        # Every other tool keeps the spec default (interacts with an open world).
        others = [n for n in verbs if n not in _CLOSED_WORLD_TOOLS]
        assert len(others) > 250
        for name in others:
            assert _hints(annotations_for(name))["openWorldHint"] is True, name

    def test_title_derivation(self):
        from npg_mcp.toolsets import _tool_title

        assert _tool_title("npg_update_proxy_host_waf") == "NPG Update Proxy Host WAF"
        assert _tool_title("npg_list_dns_providers") == "NPG List DNS Providers"
        assert _tool_title("npg_ban_ip") == "NPG Ban IP"
        assert _tool_title("npg_get_auth_sso_providers") == (
            "NPG Get Auth SSO Providers"
        )

    def test_every_annotation_carries_title_and_all_hints(self):
        from npg_mcp.toolsets import _discover_tool_names

        keys = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
        for name in _discover_tool_names():
            hints = _hints(annotations_for(name))
            assert hints["title"].startswith("NPG "), name
            for key in keys:
                assert isinstance(hints[key], bool), (name, key)

    def test_annotations_reach_served_tools_list(self):
        served = self._served()
        assert len(served) == 308
        assert [n for n, t in served.items() if t.annotations is None] == []
        for name, tool in served.items():
            expected = _hints(annotations_for(name))
            served_hints = _hints(tool.annotations)
            for key in (
                "title",
                "readOnlyHint",
                "destructiveHint",
                "idempotentHint",
                "openWorldHint",
            ):
                assert served_hints[key] == expected[key], (name, key)
            # the display title is also exposed on the tool itself
            assert tool.title == expected["title"], name

    def test_unknown_tool_has_no_annotations(self):
        assert annotations_for("npg_not_a_tool") is None

    def test_annotate_tools_is_idempotent(self):
        import npg_mcp.main as main_mod

        assert annotate_tools(main_mod.mcp) == 308
        assert annotate_tools(main_mod.mcp) == 308

    def test_annotate_tools_never_raises_on_broken_tool_manager(self):
        class Broken:
            @property
            def _tool_manager(self):
                raise RuntimeError("boom")

        assert annotate_tools(Broken()) == 0

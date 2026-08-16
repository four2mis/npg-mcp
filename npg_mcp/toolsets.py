"""Layered toolset exposure for the npg-mcp MCP server.

Users can vary the number and scope of tools exposed to the MCP client by
setting ``NPG_TOOL_LEVEL`` in the environment (e.g. in ``.env``):

* ``read``     — 129 strictly read-only tools (GET-only namespaces:
                 get/list/view/download/check/detect). For monitoring or
                 read-only agents that must not mutate NPG state.
* ``standard`` — 228 tools: everything except the 46 destructive tools
                 (all ``delete_*``/``remove_*``, bans, restores, password /
                 role / email changes, token revocation, cleanup, reset,
                 session termination, log rotation). For everyday admin work.
* ``full``     — all 274 tools (the default; unchanged from legacy behavior).

The level is applied at startup in ``main()`` via :meth:`configure_toolset`,
which removes the hidden tools from the FastMCP tool manager *before* the
server starts, so hidden tools are neither listed nor callable. The tool
counts are exact at commit time and are verified by the pipeline's static
checks (see the ``tier_allowed`` helper — used by tests, not by the server).
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("npg_mcp.toolsets")

LEVEL_ENV = "NPG_TOOL_LEVEL"
DEFAULT_LEVEL = "full"
VALID_LEVELS = ("read", "standard", "full")

# Every tool whose name starts with one of these prefixes is treated as
# read-only. Derived from npg_mcp/main.py naming contract (2026-08-16):
# all get/list/view/scan/check/detect tools call NPG GET endpoints only.
_READ_NAME_RE = re.compile(r"^npg_(get|list|view|download|check|detect)")

# 46 destructive tools hidden by the "standard" level. Derived from
# npg_mcp/main.py (2026-08-16). Keep in sync when tools are added/removed:
# re-run scripts/classify via the pipeline scan to regenerate this list.
DESTRUCTIVE_TOOLS = frozenset(
    {
        "npg_ban_ip",
        "npg_bulk_unban_ips",
        "npg_cleanup_logs",
        "npg_cleanup_system_logs",
        "npg_delete_access_list",
        "npg_delete_api_token",
        "npg_delete_auth_provider",
        "npg_delete_backup",
        "npg_delete_certificate",
        "npg_delete_certificate_errors",
        "npg_delete_cloud_provider",
        "npg_delete_ddns_record",
        "npg_delete_dns_provider",
        "npg_delete_exploit_rule",
        "npg_delete_filter_subscription",
        "npg_delete_global_uri_block_rule",
        "npg_delete_log_file",
        "npg_delete_log_filter_preset",
        "npg_delete_notification_channel",
        "npg_delete_proxy_host",
        "npg_delete_proxy_host_bot_filter",
        "npg_delete_proxy_host_challenge",
        "npg_delete_proxy_host_fail2ban",
        "npg_delete_proxy_host_geo",
        "npg_delete_proxy_host_rate_limit",
        "npg_delete_proxy_host_security_headers",
        "npg_delete_proxy_host_upstream",
        "npg_delete_proxy_host_uri_block",
        "npg_delete_proxy_host_uri_block_rule",
        "npg_delete_redirect_host",
        "npg_delete_role",
        "npg_delete_sso_provider",
        "npg_delete_user",
        "npg_end_user_sessions",
        "npg_remove_exploit_rule_exclusion_from_host",
        "npg_remove_exploit_rule_global_exclusion",
        "npg_remove_filter_subscription_entry_exclusion",
        "npg_remove_filter_subscription_exclusion",
        "npg_reset_settings",
        "npg_restore_backup",
        "npg_revoke_api_token",
        "npg_rotate_log_file",
        "npg_set_user_email",
        "npg_set_user_password",
        "npg_set_user_role",
        "npg_upload_restore_backup",
    }
)


def resolve_level(level: str | None = None) -> str:
    """Normalize an NPG_TOOL_LEVEL value; unknown values fall back to full."""
    raw = (level if level is not None else os.environ.get(LEVEL_ENV, "")).strip().lower()
    if raw not in VALID_LEVELS:
        if raw:
            logger.warning("Unknown NPG_TOOL_LEVEL=%r — falling back to 'full'", raw)
        return DEFAULT_LEVEL
    return raw


def tier_allowed(tool_names: set[str], level: str) -> set[str]:
    """Return the subset of *tool_names* allowed at *level*.

    Pure function, no mcp dependency — easy to unit-test.
    """
    if level == "full":
        return set(tool_names)
    if level == "standard":
        return {n for n in tool_names if n not in DESTRUCTIVE_TOOLS}
    # read
    return {n for n in tool_names if _READ_NAME_RE.match(n)}


def configure_toolset(mcp, level: str | None = None) -> int:
    """Remove every tool hidden by the selected level from *mcp*.

    Must be called after all tools are registered (module import) and before
    the transport starts. Removing a tool makes it unknown to both
    ``tools/list`` and ``tools/call``. Returns the number of remaining tools.

    Uses ``mcp.list_tools()`` to discover registered names; identity is by
    tool name. Missing/unknown names are skipped defensively.
    """
    level = resolve_level(level)
    registered = mcp._tool_manager.list_tools()
    names = {t.name for t in registered}
    keep = tier_allowed(names, level)
    removed = 0
    for name in names - keep:
        try:
            mcp.remove_tool(name)
            removed += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("toolsets: could not remove %r: %s", name, exc)
    logger.info("NPG_TOOL_LEVEL=%s: exposing %d of %d tools", level, len(keep), len(names))
    return len(keep)
"""Layered toolset exposure for the npg-mcp MCP server.

Users can vary the number and scope of tools exposed to the MCP client by
setting ``NPG_TOOL_LEVEL`` in the environment (e.g. in ``.env``):

* ``read``     — read-only tools (GET-only namespaces: get/list/view/
                 download/check/detect). For monitoring or read-only agents
                 that must not mutate NPG state.
* ``standard`` — everything except the destructive tools. For everyday admin
                 work.
* ``full``     — all tools (the default; unchanged from legacy behavior).

The level is applied at startup in ``main()`` via :meth:`configure_toolset`,
which removes the hidden tools from the FastMCP tool manager *before* the
server starts, so hidden tools are neither listed nor callable. The tool
counts are exact at commit time and are verified by the pipeline's static
checks (see the ``tier_allowed`` helper — used by tests, not by the server).

Destructive-tool naming convention
----------------------------------
A tool is classified as *destructive* (hidden at the ``standard`` level)
purely from its name prefix, per the regex ``_DESTRUCTIVE_NAME_RE`` below:

    ^npg_(delete_|remove_|ban_|bulk_unban_|cleanup_|end_user_sessions|
         reset_|restore_|revoke_|rotate_log|set_user_(password|role|email)|
         upload_restore_backup)

That is: any tool whose name begins ``npg_delete_`` / ``npg_remove_`` /
``npg_ban_`` / ``npg_bulk_unban_`` / ``npg_cleanup_`` / ``npg_reset_`` /
``npg_restore_`` / ``npg_revoke_`` / ``npg_rotate_log_``, or the exact tools
``npg_end_user_sessions``, ``npg_set_user_password`` / ``npg_set_user_role`` /
``npg_set_user_email``, or ``npg_upload_restore_backup`` — is destructive.
These correspond to irreversible or high-impact state mutations in the NPG
API (deletes, removes, IP bans, resets, restores, revocations, session
termination, credential changes, and backup restore).

Two escape-hatch sets let the naming contract overrule the regex for edge
cases without changing the regex itself:

* ``_DESTRUCTIVE_ALLOWLIST`` — names that *match* the regex but are NOT
  destructive. Empty; document any entry with a comment.
* ``_DESTRUCTIVE_DENYLIST``  — names that do NOT match the regex but ARE
  destructive. Currently contains ``npg_bulk_delete_proxy_hosts`` (a bulk
  delete whose ``bulk_`` prefix the regex deliberately does not match, so it
  is listed here to keep it out of the ``standard`` tier); document any
  entry with a comment.

``DESTRUCTIVE_TOOLS`` is derived at import time by applying the regex (minus
allowlist, plus denylist) to every registered tool name discovered from
``npg_mcp/main.py``. Do not hand-edit it — update the regex or one of the
two lists instead.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("npg_mcp.toolsets")

LEVEL_ENV = "NPG_TOOL_LEVEL"
DEFAULT_LEVEL = "full"
VALID_LEVELS = ("read", "standard", "full")

# Every tool whose name starts with one of these prefixes is treated as
# read-only. Derived from npg_mcp/main.py naming contract (2026-08-16):
# all get/list/view/scan/check/detect tools call NPG GET endpoints only.
_READ_NAME_RE = re.compile(r"^npg_(get|list|view|download|check|detect)")

# Destructive-prefix regex — see "Destructive-tool naming convention" in the
# module docstring. A tool is destructive iff its name matches this regex,
# adjusted by the allowlist/denylist below.
_DESTRUCTIVE_NAME_RE = re.compile(
    r"^npg_(delete_|remove_|ban_|bulk_unban_|cleanup_|end_user_sessions|"
    r"reset_|restore_|revoke_|rotate_log|set_user_(password|role|email)|"
    r"upload_restore_backup)"
)

# Names that match _DESTRUCTIVE_NAME_RE but are NOT destructive.
# (none currently — every regex-matching tool is genuinely destructive)
_DESTRUCTIVE_ALLOWLIST: frozenset[str] = frozenset()

# Names that do NOT match _DESTRUCTIVE_NAME_RE but ARE destructive.
# Each entry is documented with the reason it cannot be matched by the regex.
# (The regex deliberately matches the existing `npg_bulk_unban_` prefix but
# NOT `npg_bulk_*` in general — a hypothetical future bulk-update tool must
# not be hidden. `npg_bulk_delete_proxy_hosts` deletes proxy hosts, so it is
# destructive and is listed here explicitly to keep it out of the `standard`
# tier.)
_DESTRUCTIVE_DENYLIST: frozenset[str] = frozenset(
    {
        # Deletes N proxy hosts in one call (same DELETE endpoint as
        # npg_delete_proxy_host). Name starts with bulk_, not delete_, so the
        # regex alone would leak it into `standard` — the denylist closes that.
        "npg_bulk_delete_proxy_hosts",
    }
)


def _discover_tool_names() -> set[str]:
    """Return every registered tool name from npg_mcp/main.py.

    toolsets.py must not import main.py (main imports toolsets — a cycle), so
    it discovers names by parsing the ``@mcp.tool(name="...")`` decorators in
    the co-located main.py source, the same source of truth the pipeline's
    tool-count checks use.
    """
    main_py = Path(__file__).resolve().parent / "main.py"
    try:
        source = main_py.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - defensive
        logger.warning("toolsets: cannot read %s — destructive set is empty", main_py)
        return set()
    return set(re.findall(r'@mcp\.tool\(name="([^"]+)"', source))


# Derived at import time from the naming convention. Regex matches are the
# destructive set, minus allowlist, plus denylist.
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        name
        for name in _discover_tool_names()
        if _DESTRUCTIVE_NAME_RE.match(name)
    }
    | _DESTRUCTIVE_DENYLIST
) - _DESTRUCTIVE_ALLOWLIST


def resolve_level(level: str | None = None) -> str:
    """Normalize an NPG_TOOL_LEVEL value; unknown values fall back to full."""
    raw = (
        level if level is not None else os.environ.get(LEVEL_ENV, "")
    ).strip().lower()
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
    logger.info(
        "NPG_TOOL_LEVEL=%s: exposing %d of %d tools", level, len(keep), len(names)
    )
    return len(keep)

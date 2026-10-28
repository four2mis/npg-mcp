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

MCP ToolAnnotations
-------------------
Every registered tool also gets standard MCP ``ToolAnnotations``
(``readOnlyHint`` / ``destructiveHint`` / ``idempotentHint`` /
``openWorldHint`` + a derived ``title``) attached at startup by
:func:`annotate_tools`. Classification is derived, not hand-assigned: the HTTP
verbs each tool body calls are AST-harvested from ``main.py`` and combined with
the destructive-name set above. Annotations are additive client-facing
metadata — they never change execution, signatures, or descriptions — but they
let MCP clients filter read-only tools, warn before destructive calls, and
batch idempotent ones.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from mcp.types import ToolAnnotations

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


# ── MCP ToolAnnotations ──────────────────────────────────────────────
#
# Classification rules (derived — there is deliberately NO hand-maintained
# 308-name table):
#
# * ``readOnlyHint``    — True iff every HTTP route the tool body calls is a
#   read verb (``get`` / ``get_text`` / ``get_bytes``) and the tool is not in
#   ``_READONLY_DENYLIST`` (documented side-effecting "check" probes).
# * ``destructiveHint`` — True iff the name is in :data:`DESTRUCTIVE_TOOLS`;
#   read-only tools are never destructive.
# * ``idempotentHint``  — True for read verbs and ``put`` (repeating the call
#   reaches the same end state); False for ``post`` / ``post_file`` / ``delete``
#   (creates append rows, tests trigger side effects, a repeat delete 404s).
# * ``openWorldHint``   — False only for the closed-catalog reads in
#   ``_CLOSED_WORLD_TOOLS`` (fixed enumerations served from NPG's own DB);
#   True everywhere else, because the admin API reaches upstreams, ACME, DNS
#   providers, and Telegram.

# HTTP verbs that cannot modify NPG state, and their mutating counterparts.
# Mirrors npg_mcp.client.NPGClient's public method names.
_READ_VERBS: frozenset[str] = frozenset({"get", "get_text", "get_bytes"})
_MUTATING_VERBS: frozenset[str] = frozenset({"post", "post_file", "put", "delete"})
_ALL_VERBS: frozenset[str] = _READ_VERBS | _MUTATING_VERBS

# GET-routed tools that DO have side effects beyond reading, so they must not
# advertise ``readOnlyHint=true``. Each entry needs a reason.
_READONLY_DENYLIST: frozenset[str] = frozenset(
    {
        # GET /test/backup-restore creates a throwaway backup row, lists it, and
        # deletes it — a transient DB write, not a pure read.
        "npg_check_backup_restore",
    }
)

# Pure-catalog reads: fixed enumerations/registries served from NPG's own
# database (no upstream, DNS, ACME, or Telegram interaction), so
# ``openWorldHint=false``. Anything not listed keeps the spec default (true).
_CLOSED_WORLD_TOOLS: frozenset[str] = frozenset(
    {
        "npg_get_audit_log_actions",
        "npg_get_audit_log_resource_types",
        "npg_get_bots_known",
        "npg_get_catalog",
        "npg_get_permission_areas",
        "npg_get_security_headers_presets",
        "npg_get_settings_presets",
        "npg_get_system_log_levels",
        "npg_get_system_log_sources",
        "npg_get_waf_test_patterns",
        "npg_list_countries",
    }
)

# Words in a tool name that are acronyms and must render uppercase in titles.
_ACRONYMS: frozenset[str] = frozenset(
    {
        "acme",
        "ai",
        "api",
        "csv",
        "ddns",
        "dns",
        "geoip",
        "http",
        "https",
        "id",
        "ip",
        "ips",
        "json",
        "mcp",
        "pem",
        "sso",
        "ssl",
        "tcp",
        "tls",
        "ui",
        "uri",
        "uris",
        "url",
        "urls",
        "uuid",
        "waf",
        "zip",
    }
)


def _tool_name_from_decorators(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """Return the ``name=`` kwarg of an ``@mcp.tool(...)`` decorator, if any."""
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        if not (isinstance(dec.func, ast.Attribute) and dec.func.attr == "tool"):
            continue
        for kw in dec.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                value = kw.value.value
                if isinstance(value, str):
                    return value
    return None


@lru_cache(maxsize=1)
def _tool_verbs() -> dict[str, frozenset[str]]:
    """Map every registered tool name to the HTTP verbs its body calls.

    Parses ``npg_mcp/main.py`` with the stdlib AST (toolsets.py must not import
    main.py — main imports toolsets — so this mirrors ``_discover_tool_names``).
    Recognizes both call conventions used in the module: ``_api(c.<verb>, ...)``
    (including ``_api(_get_client().get, ...)``) and direct ``c.<verb>(...)``.
    """
    main_py = Path(__file__).resolve().parent / "main.py"
    try:
        tree = ast.parse(main_py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:  # pragma: no cover - defensive
        logger.warning(
            "toolsets: cannot parse %s (%s) — annotations lose route data",
            main_py,
            exc,
        )
        return {}

    verbs_by_tool: dict[str, frozenset[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = _tool_name_from_decorators(node)
        if name is None:
            continue
        verbs: set[str] = set()
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            if isinstance(func, ast.Name) and func.id == "_api" and call.args:
                first = call.args[0]
                if isinstance(first, ast.Attribute) and first.attr in _ALL_VERBS:
                    verbs.add(first.attr)
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in _ALL_VERBS
                and isinstance(func.value, ast.Name)
                and func.value.id == "c"
            ):
                verbs.add(func.attr)
        verbs_by_tool[name] = frozenset(verbs)
    return verbs_by_tool


def _tool_title(name: str) -> str:
    """Derive a human-readable display title from a tool name.

    ``npg_update_proxy_host_waf`` → ``NPG Update Proxy Host WAF``; known
    acronyms (``dns``, ``api``, ``sso``, …) render uppercase.
    """
    stem = name[4:] if name.startswith("npg_") else name
    words = [
        word.upper() if word in _ACRONYMS else word.capitalize()
        for word in stem.split("_")
        if word
    ]
    return f"NPG {' '.join(words)}" if words else name


def annotations_for(name: str) -> ToolAnnotations | None:
    """Return the MCP ToolAnnotations for *name*, or None if it is unknown.

    None means "no route data was harvested for this tool" — callers log it so
    a new tool with an unusual call convention cannot silently ship without
    annotations. Pure function apart from the cached AST parse.
    """
    verbs = _tool_verbs().get(name)
    if verbs is None:
        return None
    destructive = name in DESTRUCTIVE_TOOLS
    read_only = bool(verbs) and verbs <= _READ_VERBS and not destructive
    if name in _READONLY_DENYLIST:
        read_only = False
    idempotent = bool(verbs) and not destructive and verbs <= (_READ_VERBS | {"put"})
    # Build via model_validate on the camelCase wire names: mcp 1.x declares the
    # fields as ``readOnlyHint`` (camelCase) while mcp 2.x renames them to
    # snake_case with camelCase aliases, so alias-based validation is the only
    # construction that works across the supported ``mcp>=1.29,<2`` range.
    return ToolAnnotations.model_validate(
        {
            "title": _tool_title(name),
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": name not in _CLOSED_WORLD_TOOLS,
        }
    )


def annotate_tools(mcp) -> int:
    """Attach ToolAnnotations to every tool registered on *mcp*.

    Called once from ``main()`` after module-level registration and before the
    transport starts (order relative to :func:`configure_toolset` does not
    matter: removed tools are simply never listed). Mutating the FastMCP
    ``Tool`` objects is enough — ``FastMCP.list_tools()`` copies
    ``info.annotations`` (and ``info.title``) into every served
    ``tools/list`` entry, so clients see the hints on connect.

    Returns the number of tools annotated. Never raises: a tool that cannot be
    classified is left unannotated and logged.
    """
    try:
        registered = mcp._tool_manager.list_tools()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("toolsets: cannot list tools to annotate: %s", exc)
        return 0

    applied = 0
    unclassified: list[str] = []
    for tool in registered:
        annotations = annotations_for(tool.name)
        if annotations is None:
            unclassified.append(tool.name)
            continue
        try:
            tool.annotations = annotations
            if getattr(tool, "title", None) is None:
                tool.title = annotations.title
            applied += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("toolsets: cannot annotate %r: %s", tool.name, exc)
    if unclassified:
        logger.warning(
            "toolsets: %d tool(s) left unannotated (no route data): %s",
            len(unclassified),
            ", ".join(sorted(unclassified)),
        )
    logger.info(
        "toolsets: attached MCP ToolAnnotations to %d of %d tools",
        applied,
        len(registered),
    )
    return applied

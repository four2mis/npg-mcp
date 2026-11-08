#!/usr/bin/env python3
"""Regenerate ``npg_mcp/permission_map.py`` — the tool → NPG-permission map.

Background
----------
NPG authorises every API route through ONE registry,
``api/internal/middleware/permissions.go`` (upstream repo
``svrforum/NginxProxyGuard``)::

    routePermissions["GET /api/v1/proxy-hosts/:id"] = "proxy:read"
    PublicRoutes["GET /api/v1/status"]             = true   # no permission
    SelfRoutes["GET /api/v1/auth/me"]              = true   # own account

A per-tool map cannot be *guessed* from a tool name, and the swagger spec only
annotates a handful of routes (26 of 318 operations carry a "Requires `scope`"
sentence), so this script reads the authoritative Go registry instead and
projects it onto the MCP surface:

    tool  →  (HTTP verb, path template harvested from main.py via AST)
          →  normalised route key ("GET /api/v1/proxy-hosts/*")
          →  required permission ("proxy:read")

Rules
-----
* ``ALL`` semantics: a tool requires the union of the permissions of every
  route its body calls, and is exposed only when the caller holds all of them.
  Read-modify-write tools therefore demand the read scope as well as the write
  scope they actually need.
* Permission-free routes (upstream ``PublicRoutes`` / ``SelfRoutes``) map to an
  empty tuple, so those tools are never hidden.
* Tools whose route cannot be resolved statically are listed in
  ``MANUAL_OVERRIDES`` below with the reviewed value and a reason — the
  ``--check`` mode fails when a registered tool has no entry at all, so a new
  tool cannot silently slip past the map (a missing entry would otherwise
  fail OPEN and quietly weaken the filter).
* Route normalisation collapses every path-parameter segment to ``*``. If two
  upstream routes normalise to the same key with different permissions, the
  generator refuses to guess and reports the collision.

Usage
-----
    # Review (prints the distribution + any unmapped/stale entries)
    python3 scripts/derive_tool_permissions.py --upstream /path/to/NginxProxyGuard

    # Rewrite npg_mcp/permission_map.py
    python3 scripts/derive_tool_permissions.py --upstream /path --write

    # Gate (exit 1 on drift — same contract as the doc regenerator)
    python3 scripts/derive_tool_permissions.py --upstream /path --check

``--upstream`` may be omitted when ``npg_mcp/permission_map.py`` already exists:
the committed ``ROUTE_PERMISSIONS`` table is then reused, which is enough for
any tool that maps onto an already-known route. Refresh from upstream whenever
NPG adds or re-scopes endpoints.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

VERBS = {"get", "get_text", "get_bytes", "post", "post_file", "put", "delete"}
HTTP_OF = {
    "get": "GET",
    "get_text": "GET",
    "get_bytes": "GET",
    "post": "POST",
    "post_file": "POST",
    "put": "PUT",
    "delete": "DELETE",
}

OUTPUT_NAME = "permission_map.py"

# ── Manual review table ────────────────────────────────────────────────
# Tools whose route(s) cannot be resolved from main.py's AST because the path
# is composed at runtime (helper functions, loops over sections). Each entry
# is a reviewed decision, not a guess — keep the reason with the entry.
MANUAL_OVERRIDES: dict[str, tuple[tuple[str, ...], str]] = {
    "npg_get_proxy_host_full": (
        ("proxy:read", "waf:read"),
        "11 section GETs: 10 x /api/v1/proxy-hosts/{id}/... (proxy:read) "
        "+ /api/v1/waf/hosts/{id}/config (waf:read), built by "
        "_proxy_host_section_paths() at runtime",
    ),
    "npg_bulk_get_proxy_host_full": (
        ("proxy:read", "waf:read"),
        "per-host fan-out over the same 11 sections as npg_get_proxy_host_full",
    ),
    "npg_export_proxy_host": (
        ("proxy:read", "waf:read"),
        "composes the same 11 sections as npg_get_proxy_host_full (read-only)",
    ),
    "npg_bulk_export_proxy_hosts": (
        ("proxy:read", "waf:read"),
        "per-host fan-out over the same 11 sections as npg_export_proxy_host "
        "via _build_export_bundle(), so its section paths are built at runtime "
        "and the AST cannot see them; without this entry the generator emits an "
        "empty tuple and the scope filter exposes a proxy-config dump to any "
        "token",
    ),
    "npg_import_proxy_host": (
        ("proxy:write",),
        "POST /api/v1/proxy-hosts + per-host sub-config writes + "
        "POST /api/v1/proxy-hosts/sync; section paths are built at runtime, so "
        "proxy:write is the reviewed floor for the whole import",
    ),
    "npg_get_stack_features": (
        (),
        "REPORT-ONLY capability probe whose contract is 403-as-data: it must "
        "stay callable so a scope-filtered server can still report what the "
        "filter hid (hidden_by_scope). Gating it would make the filter "
        "unreportable exactly when the token is most restricted",
    ),
}


# ── upstream Go source parsing ─────────────────────────────────────────


def _go_block(src: str, header: str) -> str:
    """Return the body between the braces of ``header … { … }``."""
    start = src.index(header)
    body_start = src.index("{", start)
    depth = 0
    for i in range(body_start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[body_start + 1 : i]
    raise ValueError(f"unbalanced braces after {header!r}")


def parse_upstream(permissions_go: Path) -> tuple[dict[str, str], set[str]]:
    """Parse upstream routePermissions + the permission-free route sets."""
    src = permissions_go.read_text(encoding="utf-8")
    perms: dict[str, str] = {}
    for key, value in re.findall(
        r'"([A-Z]+ [^"]+)"\s*:\s*"([^"]+)"',
        _go_block(src, "var routePermissions = map[string]string"),
    ):
        perms[key] = value
    free: set[str] = set()
    for var in ("PublicRoutes", "SelfRoutes"):
        block = _go_block(src, f"var {var} = map[string]bool")
        free |= set(re.findall(r'"([A-Z]+ [^"]+)"\s*:\s*true', block))
    return perms, free


# ── route normalisation ────────────────────────────────────────────────


def normalize_path(path: str) -> str:
    """Collapse every parameter segment to ``*``.

    ``/api/v1/proxy-hosts/:id`` (Go) and ``/api/v1/proxy-hosts/{}`` (main.py
    f-string) both become ``/api/v1/proxy-hosts/*``.
    """
    segments = []
    for segment in path.strip().rstrip("/").split("/"):
        if not segment:
            continue
        if segment.startswith(":") or (
            segment.startswith("{") and segment.endswith("}")
        ):
            segments.append("*")
        else:
            segments.append(segment)
    return "/" + "/".join(segments)


def normalize_route(route: str) -> str:
    """Normalise a ``"METHOD /path"`` key."""
    method, _, path = route.partition(" ")
    return f"{method} {normalize_path(path)}"


# ── main.py harvesting ─────────────────────────────────────────────────


def _tool_name(node: ast.AST) -> str | None:
    """Return the ``name=`` kwarg of an ``@mcp.tool(...)`` decorator."""
    for dec in getattr(node, "decorator_list", []):
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


def _path_template(node: ast.AST, locals_: dict[str, str]) -> str | None:
    """Resolve a path expression to a template string, or None if dynamic."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                out.append(str(part.value))
            else:
                out.append("{}")
        return "".join(out)
    if isinstance(node, ast.Name):
        return locals_.get(node.id)
    return None


def harvest_tool_routes(main_py: Path) -> dict[str, list[tuple[str, str | None]]]:
    """Map every registered tool to the (verb, path template) calls it makes."""
    tree = ast.parse(main_py.read_text(encoding="utf-8"))
    tool_routes: dict[str, list[tuple[str, str | None]]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = _tool_name(node)
        if name is None:
            continue
        # One level of local-name indirection (``path = f"/api/v1/..."``).
        locals_: dict[str, str] = {}
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Assign)
                and len(sub.targets) == 1
                and isinstance(sub.targets[0], ast.Name)
            ):
                template = _path_template(sub.value, locals_)
                if template is not None:
                    locals_[sub.targets[0].id] = template
        routes: list[tuple[str, str | None]] = []
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            verb: str | None = None
            path_node: ast.AST | None = None
            if isinstance(func, ast.Name) and func.id == "_api" and call.args:
                first = call.args[0]
                if isinstance(first, ast.Attribute) and first.attr in VERBS:
                    verb = first.attr
                elif (
                    isinstance(first, ast.Call)
                    and isinstance(first.func, ast.Attribute)
                    and first.func.attr in VERBS
                ):
                    verb = first.func.attr
                if verb is not None and len(call.args) > 1:
                    path_node = call.args[1]
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in VERBS
                and isinstance(func.value, ast.Name)
                and func.value.id == "c"
                and call.args
            ):
                verb = func.attr
                path_node = call.args[0]
            if verb is not None and path_node is not None:
                routes.append((verb, _path_template(path_node, locals_)))
        tool_routes[name] = routes
    return tool_routes


# ── projection ─────────────────────────────────────────────────────────


def build_maps(
    tool_routes: dict[str, list[tuple[str, str | None]]],
    route_permissions: dict[str, str],
    free_routes: set[str],
) -> tuple[dict[str, tuple[str, ...]], dict[str, list[str]], list[str]]:
    """Project the route registry onto tools.

    Returns ``(tool_permissions, unresolved, collisions)``.
    """
    by_key: dict[str, set[str | None]] = {}
    for route, permission in route_permissions.items():
        by_key.setdefault(normalize_route(route), set()).add(permission)
    for route in free_routes:
        by_key.setdefault(normalize_route(route), set()).add(None)

    collisions = [
        key
        for key, values in by_key.items()
        if len(values) > 1 or (None in values and len(values) > 1)
    ]

    tool_permissions: dict[str, tuple[str, ...]] = {}
    unresolved: dict[str, list[str]] = {}
    for name, routes in tool_routes.items():
        if name in MANUAL_OVERRIDES:
            tool_permissions[name] = MANUAL_OVERRIDES[name][0]
            continue
        needed: set[str] = set()
        problems: list[str] = []
        for verb, template in routes:
            if template is None:
                problems.append(f"{verb} <dynamic path>")
                continue
            key = f"{HTTP_OF[verb]} {normalize_path(template)}"
            values = by_key.get(key)
            if values is None:
                problems.append(f"{key} <not in upstream registry>")
                continue
            if len(values) > 1:
                problems.append(f"{key} <ambiguous: {sorted(v or '' for v in values)}>")
                continue
            permission = next(iter(values))
            if permission is not None:
                needed.add(permission)
        if problems:
            unresolved[name] = problems
        else:
            tool_permissions[name] = tuple(sorted(needed))
    return tool_permissions, unresolved, sorted(collisions)


# ── emit / compare ─────────────────────────────────────────────────────


def render(
    tool_permissions: dict[str, tuple[str, ...]],
    route_permissions: dict[str, str],
    free_routes: set[str],
) -> str:
    """Render the generated module."""
    lines: list[str] = [
        '"""Route → permission maps for scope-aware tool filtering.',
        "",
        "GENERATED FILE — do not hand-edit. Regenerate with::",
        "",
        "    python3 scripts/derive_tool_permissions.py \\",
        "        --upstream /path/to/NginxProxyGuard --write",
        "",
        "``NPG_TOOL_SCOPE_FILTER`` (default off) uses these tables to expose only",
        "the tools the configured NPG_API_TOKEN's permissions actually cover —",
        "see ``npg_mcp/scopefilter.py``. The permission strings are NPG's own",
        "(``proxy:read``, ``waf:write``, …): one of the 15 legacy token scopes or",
        "one of the 16 ``area:verb`` permissions they expand into.",
        "",
        "``TOOL_PERMISSIONS`` keys are MCP tool names; values are the permission",
        "strings every route the tool calls requires (ALL semantics). An empty",
        "tuple means the tool calls only permission-free routes (public or",
        "self-service endpoints), so it is never hidden by the scope filter.",
        "",
        "``ROUTE_PERMISSIONS`` is the normalised upstream registry this file was",
        "generated from, kept so the map can be re-derived offline:",
        "``METHOD /api/v1/path/*`` → permission, and ``None`` for public/self",
        "routes. Path-parameter segments are collapsed to ``*``.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "# Upstream route registry, normalised. None = no permission required.",
        "ROUTE_PERMISSIONS: dict[str, str | None] = {",
    ]
    merged: dict[str, str | None] = {}
    for route, permission in route_permissions.items():
        merged[normalize_route(route)] = permission
    for route in free_routes:
        merged.setdefault(normalize_route(route), None)
    for key in sorted(merged):
        value = merged[key]
        rendered = "None" if value is None else f'"{value}"'
        lines.append(f'    "{key}": {rendered},')
    lines += [
        "}",
        "",
        "# Tool → permission strings required for every route the tool calls.",
        "TOOL_PERMISSIONS: dict[str, tuple[str, ...]] = {",
    ]
    for name in sorted(tool_permissions):
        values = ", ".join(f'"{p}"' for p in tool_permissions[name])
        if len(tool_permissions[name]) == 1:
            values += ","
        lines.append(f'    "{name}": ({values}),')
    lines += ["}", ""]
    return "\n".join(lines)


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Regenerate npg_mcp/permission_map.py (tool → NPG permissions)"
    )
    parser.add_argument("--repo", default=str(repo), help="npg-mcp checkout root")
    parser.add_argument(
        "--upstream",
        default=None,
        help="path to an NginxProxyGuard checkout (uses "
        "api/internal/middleware/permissions.go)",
    )
    parser.add_argument("--write", action="store_true", help="rewrite the map file")
    parser.add_argument("--check", action="store_true", help="exit 1 on drift")
    args = parser.parse_args()

    root = Path(args.repo)
    main_py = root / "npg_mcp" / "main.py"
    out_path = root / "npg_mcp" / OUTPUT_NAME

    route_permissions: dict[str, str] = {}
    free_routes: set[str] = set()
    if args.upstream:
        permissions_go = (
            Path(args.upstream) / "api" / "internal" / "middleware" / "permissions.go"
        )
        if not permissions_go.exists():
            print(f"❌ {permissions_go} not found — check --upstream", file=sys.stderr)
            return 2
        route_permissions, free_routes = parse_upstream(permissions_go)
        print(
            f"upstream registry: {len(route_permissions)} route permissions, "
            f"{len(free_routes)} permission-free routes"
        )
    else:
        if not out_path.exists():
            print(
                "❌ --upstream is required when the map file does not exist yet",
                file=sys.stderr,
            )
            return 2
        sys.path.insert(0, str(root))
        from npg_mcp.permission_map import ROUTE_PERMISSIONS as committed

        for key, permission in committed.items():
            if permission is None:
                free_routes.add(key)
            else:
                route_permissions[key] = permission
        print(
            f"committed registry: {len(route_permissions)} route permissions, "
            f"{len(free_routes)} permission-free routes (no --upstream given)"
        )

    tool_routes = harvest_tool_routes(main_py)
    tool_permissions, unresolved, collisions = build_maps(
        tool_routes, route_permissions, free_routes
    )

    print(f"tools in main.py: {len(tool_routes)}")
    print(f"mapped: {len(tool_permissions)}; unresolved: {len(unresolved)}")
    if collisions:
        print("⚠️  normalized-route collisions (refusing to guess):")
        for key in collisions:
            print(f"   {key}")
    for name, problems in sorted(unresolved.items()):
        print(f"   UNRESOLVED {name}: {problems}")

    missing = sorted(set(tool_routes) - set(tool_permissions))
    stale = sorted(set(tool_permissions) - set(tool_routes))
    manual_stale = sorted(set(MANUAL_OVERRIDES) - set(tool_routes))

    distribution: dict[str, int] = {}
    for values in tool_permissions.values():
        key = " + ".join(values) if values else "<permission-free>"
        distribution[key] = distribution.get(key, 0) + 1
    print("permission distribution:")
    for key in sorted(distribution):
        print(f"   {key}: {distribution[key]}")

    problems = False
    if missing:
        problems = True
        print(f"❌ {len(missing)} tool(s) have no entry in the map: {missing[:10]}")
    if stale:
        problems = True
        print(
            f"❌ {len(stale)} map entr(ies) name tools that no longer exist: "
            f"{stale[:10]}"
        )
    if manual_stale:
        problems = True
        print(f"❌ MANUAL_OVERRIDES names unknown tools: {manual_stale}")
    if collisions:
        problems = True
        print("❌ route normalization collisions — resolve by hand before writing")

    rendered = render(tool_permissions, route_permissions, free_routes)

    if args.write:
        out_path.write_text(rendered, encoding="utf-8")
        print(f"✅ wrote {out_path.relative_to(root)} ({len(tool_permissions)} tools)")
        return 1 if problems else 0

    current = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
    drift = current != rendered
    if args.check:
        if drift:
            print(f"❌ {OUTPUT_NAME} is out of date — rerun with --write")
            return 1
        if problems:
            return 1
        print(f"✅ {OUTPUT_NAME} is in sync ({len(tool_permissions)} tools)")
        return 0
    if drift:
        print(f"\n{OUTPUT_NAME} would change (run with --write)")
    else:
        print(f"\n{OUTPUT_NAME} already up to date")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

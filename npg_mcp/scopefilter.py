"""Opt-in scope-aware tool filtering (``NPG_TOOL_SCOPE_FILTER``).

What it does
------------
NPG's admin API authorises every route against the caller's permissions. When
an MCP client is wired to a *scoped* API token, most of the surface it sees is
dead weight: every call outside the token's scopes answers HTTP 403. With
``NPG_TOOL_SCOPE_FILTER=1`` the server narrows its manifest at boot to the tools
the configured ``NPG_API_TOKEN`` can actually use::

    exposed = tier membership (NPG_TOOL_LEVEL) ∩ tool permissions ⊆ granted

Default is OFF, and OFF changes nothing: the manifest, the tool count and the
tier contract are exactly what they are without this module. That matters
because the tier counts are a pinned contract (README, ``.env.example``, the
pipeline's drift checks, ``tests/test_toolsets.py``) — they describe the
*full* surface, never a filtered one.

How the grant is discovered (boot snapshot, no refresh)
-------------------------------------------------------
Two endpoints, in order — both read the SAME effective grant the API enforces:

1. ``GET /api/v1/api-tokens`` — requires the literal ``apitoken:read``. The
   response is a bare array of token rows (``token_prefix`` is ``ng_`` + the
   token's first 8 characters; the secret itself is never returned). Pick the
   row whose ``token_prefix`` the configured token starts with and read its
   ``permissions``: ``"*"`` or entries from the 15 legacy resource scopes
   (``proxy:read`` … ``user:read``).
2. Fallback ``GET /api/v1/auth/me`` — a self-service route needing no
   permission. For a token caller it returns ``effective_permissions``: the
   owner role's expanded permissions intersected with the token's own scopes,
   i.e. exactly what ``CanToken`` enforces per request. This fallback is what
   makes the filter usable at all on NPG 2.65.4, where a UI-created token can
   never hold ``apitoken:read`` (``POST /api/v1/api-tokens`` accepts only ``*``
   or the 15 legacy scopes, and token checks are exact string matches — see the
   "How token permissions are matched" note below).

Matching then mirrors ``APIToken.HasPermission``: a required permission is
granted by ``"*"``, by the identical string, or by a ``family:*`` wildcard. No
legacy→area expansion and no verb hierarchy is applied to tokens (that table is
for roles).

The snapshot is taken ONCE at server start — that is deliberate (no per-request
introspection, no mid-connection manifest churn). Editing the token's scopes in
the NPG UI therefore requires an MCP restart to take effect; the boot log and
``npg_get_stack_features`` both report what the snapshot saw.

FAIL-OPEN, always
-----------------
Hiding a tool that would have worked is much worse than showing one that 403s:
a hidden ``create_*`` tool removes the only path that makes a feature exist.
So every uncertainty resolves to *expose*:

* any introspection failure — BOTH endpoints failing: a 403/timeout/transport
  error from ``/api/v1/api-tokens`` AND from ``/api/v1/auth/me``, no matching
  prefix, an ambiguous prefix (>1 row), an unset ``NPG_API_TOKEN``, or an empty
  / unparseable permissions array;
* any tool with no entry in :data:`npg_mcp.permission_map.TOOL_PERMISSIONS`
  (a freshly synced upstream endpoint cannot be accidentally hidden);
* any tool whose mapped permissions are empty (public/self-service routes).

The failure reason is logged at WARNING and reported by
:func:`hidden_by_scope`, but it never removes a tool.

Maintenance
-----------
The tool → permission map is generated, not hand-written:
``scripts/derive_tool_permissions.py`` projects NPG's own route-authorisation
registry (``api/internal/middleware/permissions.go``) onto the MCP tool bodies.
``tests/test_scopefilter.py`` fails when a registered tool is missing from the
map, so the map cannot silently fall behind the tool surface.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import npg_mcp.client as client_mod
from npg_mcp.permission_map import TOOL_PERMISSIONS

logger = logging.getLogger("npg_mcp.scopefilter")

FILTER_ENV = "NPG_TOOL_SCOPE_FILTER"

# Shape of a permission string an API token may carry: ``*``, ``area:verb`` or
# a ``area:*`` family wildcard.
_PERMISSION_RE = re.compile(r"^[a-z][a-z0-9]*:(\*|[a-z]+)$")

# Legacy resource scopes an API token may carry (GET /api-tokens/permissions).
# Kept for the "*" expansion and for validation of the introspection result.
LEGACY_SCOPES: tuple[str, ...] = (
    "proxy:read",
    "proxy:write",
    "proxy:delete",
    "certificate:read",
    "certificate:write",
    "certificate:delete",
    "waf:read",
    "waf:write",
    "logs:read",
    "settings:read",
    "settings:write",
    "backup:read",
    "backup:create",
    "backup:restore",
    "user:read",
)

# Every area:verb permission NPG knows (upstream model.PermissionAreas).
ALL_PERMISSIONS: tuple[str, ...] = (
    "dashboard:read",
    "proxy:read",
    "proxy:write",
    "proxy:delete",
    "redirect:read",
    "redirect:write",
    "redirect:delete",
    "waf:read",
    "waf:write",
    "access:read",
    "access:write",
    "authprovider:read",
    "authprovider:write",
    "certificate:read",
    "certificate:write",
    "certificate:delete",
    "dnsprovider:read",
    "dnsprovider:write",
    "dnsprovider:delete",
    "ddns:read",
    "ddns:write",
    "logs:read",
    "logs:write",
    "audit:read",
    "settings:read",
    "settings:write",
    "backup:read",
    "backup:create",
    "backup:restore",
    "apitoken:read",
    "apitoken:write",
    "user:read",
    "user:write",
    "role:read",
    "role:write",
)

# ── How token permissions are matched (verified, do not "improve") ─────
#
# API tokens are matched EXACTLY, not through the role implication table.
# Upstream ``model.APIToken.HasPermission`` accepts a required permission only
# when the token holds ``"*"``, the identical string, or a trailing
# ``family:*`` wildcard. ``model.ExpandPermissions`` (legacy scope → the area
# permissions it contains, plus the write⊃read verb hierarchy) applies to ROLE
# permissions, NOT to tokens: ``AuthzService.CanToken`` calls
# ``token.HasPermission`` directly and only then caps by the owner's role.
#
# Verified against NPG 2.65.4 on the isolated test stack: a token holding
# ``settings:read`` answers 403 ``insufficient permissions / required:
# apitoken:read`` on ``GET /api/v1/api-tokens``, and a ``read_only`` token
# (proxy/certificate/waf/logs/settings/backup read) reaches exactly those six
# areas while redirect/access/authprovider/dnsprovider/ddns/audit/dashboard/
# user/role all 403. Mirroring the role expansion here would expose ~100 tools
# that answer 403 — i.e. it would defeat the feature's purpose.
#
# So the grant is "the strings the token actually holds", expanded only for
# reporting (``expand_permissions``); the decision itself uses
# :func:`has_permission`, which mirrors ``HasPermission`` byte for byte.

# Verb hierarchy per area is deliberately NOT applied to tokens (see above).


@dataclass
class FilterState:
    """Outcome of the boot-time snapshot, for logs and reporting."""

    enabled: bool = False
    applied: bool = False
    reason: str = ""
    source: str = ""
    token_prefix: str = ""
    stored_permissions: tuple[str, ...] = ()
    granted_scopes: tuple[str, ...] = ()
    manifest_before: int = 0
    manifest_after: int = 0
    hidden_tools: tuple[str, ...] = ()
    unmapped_tools: tuple[str, ...] = field(default_factory=tuple)

    def hidden_by_scope(self) -> dict | None:
        """Report shape for ``npg_get_stack_features``.

        ``None`` when the filter is off — the field is only meaningful when
        filtering is active. When it is on but failed open, ``applied`` is
        False and ``reason`` says why.
        """
        if not self.enabled:
            return None
        return {
            "enabled": True,
            "applied": self.applied,
            "reason": self.reason,
            "snapshot": "boot",
            "source": self.source or None,
            "token_prefix": self.token_prefix or None,
            "stored_permissions": list(self.stored_permissions),
            "granted_scope_count": len(self.granted_scopes),
            "hidden_count": len(self.hidden_tools),
            "hidden_tools": list(self.hidden_tools),
            "exposed_count": self.manifest_after,
            "manifest_before": self.manifest_before,
            "unmapped_tool_count": len(self.unmapped_tools),
        }


# Latest snapshot. Process-wide and written once (from main(), before the
# transport starts), so plain module state is enough — no locking needed.
_STATE = FilterState()


def state() -> FilterState:
    """Return the boot snapshot (a default disabled state before boot)."""
    return _STATE


def hidden_by_scope() -> dict | None:
    """Return the report payload for ``npg_get_stack_features`` (None if off)."""
    return _STATE.hidden_by_scope()


def resolve_enabled(value: str | None = None) -> bool:
    """Parse ``NPG_TOOL_SCOPE_FILTER``; anything but an explicit false is off.

    Truthiness follows the project's ``NPG_DRY_RUN`` convention: unset, empty,
    ``0``, ``false`` and ``no`` are off — everything else (``1``, ``true``,
    ``yes``, ``on``, ``enabled``) turns the filter on.
    """
    raw = (value if value is not None else os.environ.get(FILTER_ENV, ""))
    return raw.strip().lower() not in ("", "0", "false", "no")


def _matches(held: str, required: str) -> bool:
    """Mirror upstream ``APIToken.HasPermission`` for one held permission.

    ``"*"`` grants everything, an identical string grants itself, and a
    trailing ``family:*`` wildcard grants its family (``proxy:*`` covers
    ``proxy:read``/``proxy:write``/``proxy:delete``). Nothing else matches —
    there is no legacy→area expansion and no verb hierarchy for tokens.
    """
    if held == "*" or held == required:
        return True
    if len(held) > 2 and held.endswith(":*"):
        return required.startswith(held[:-1])
    return False


def has_permission(stored: tuple[str, ...] | list[str], required: str) -> bool:
    """Return True when *stored* covers *required* (upstream token semantics)."""
    return any(_matches(held, required) for held in stored if isinstance(held, str))


def expand_permissions(stored: list[str] | tuple[str, ...]) -> set[str]:
    """Enumerate the concrete permissions *stored* grants — for REPORTING only.

    ``"*"`` becomes the full area catalogue plus every legacy scope; a
    ``family:*`` wildcard becomes every catalogue entry in that family plus the
    wildcard itself; everything else is itself. Exposure decisions do NOT use
    this set — they use :func:`has_permission`, so an unknown-but-valid
    permission string can never be silently dropped from a decision.
    """
    granted: set[str] = set()
    for permission in stored:
        if not isinstance(permission, str):
            continue
        if permission == "*":
            granted.update(ALL_PERMISSIONS)
            granted.update(LEGACY_SCOPES)
            continue
        granted.add(permission)
        if len(permission) > 2 and permission.endswith(":*"):
            granted.update(
                entry for entry in ALL_PERMISSIONS if entry.startswith(permission[:-1])
            )
    return granted


def required_permissions(tool_name: str) -> tuple[str, ...] | None:
    """Return the permissions *tool_name* needs, or None when unmapped.

    None means "no annotation exists" — the caller must expose the tool.
    """
    return TOOL_PERMISSIONS.get(tool_name)


def is_exposed(tool_name: str, stored: tuple[str, ...] | list[str]) -> bool:
    """Return True when every permission *tool_name* needs is granted."""
    required = TOOL_PERMISSIONS.get(tool_name)
    if required is None:
        return True  # unannotated → always exposed (fail-open)
    return all(has_permission(stored, permission) for permission in required)


def select_exposed(
    tool_names: set[str], stored: tuple[str, ...] | list[str]
) -> set[str]:
    """Return the subset of *tool_names* the grant covers."""
    return {name for name in tool_names if is_exposed(name, stored)}


def unmapped_tools(tool_names: set[str]) -> set[str]:
    """Return the tools that carry no permission annotation."""
    return {name for name in tool_names if name not in TOOL_PERMISSIONS}


def _token_rows(payload) -> list[dict] | None:
    """Normalise ``GET /api/v1/api-tokens`` into a list of token rows."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "tokens", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return None


def match_token_row(rows: list[dict], token: str) -> tuple[dict | None, str]:
    """Return ``(row, reason)`` for the token row whose prefix matches *token*.

    ``token_prefix`` is ``ng_`` plus the token's first 8 characters, so a
    prefix match is ``token.startswith(prefix)``. An empty row set or more than
    one match is reported as a reason and yields ``(None, reason)`` — the
    caller fails open rather than guessing.
    """
    if not token:
        return None, "NPG_API_TOKEN is not set"
    matches = []
    for row in rows:
        prefix = row.get("token_prefix")
        if not isinstance(prefix, str) or not prefix:
            continue
        if token.startswith(prefix):
            matches.append(row)
    if not matches:
        return None, (
            "no API-token row matches the configured token's prefix "
            "(tokens are listed per owner — the token may belong to another "
            "account, or /api/v1/api-tokens may only list the caller's own)"
        )
    if len(matches) > 1:
        prefixes = sorted(str(row.get("token_prefix")) for row in matches)
        return None, f"ambiguous token prefix — {len(matches)} rows match: {prefixes}"
    return matches[0], ""


def _usable_permissions(stored: list) -> tuple[str, ...]:
    """Return the entries of *stored* that name a real permission.

    ``"*"`` and ``area:verb`` strings are kept; anything else (empty strings,
    objects, prose) is dropped rather than granted — a malformed row must not
    silently grant nothing and hide the whole surface, and it must not smuggle
    an arbitrary string into the grant set either.
    """
    usable: list[str] = []
    for entry in stored:
        if not isinstance(entry, str):
            continue
        value = entry.strip()
        if value == "*" or _PERMISSION_RE.match(value):
            usable.append(value)
    return tuple(usable)


@dataclass
class Introspection:
    """What one introspection attempt learned about the configured token."""

    stored: tuple[str, ...] | None = None
    source: str = ""
    token_prefix: str = ""
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.stored is not None


def _from_token_row(client, token: str, path: str) -> Introspection:
    """Primary path: list the token rows and prefix-match the configured token.

    This is the mechanism that reads the row's own ``permissions`` array, but it
    requires the literal ``apitoken:read`` permission — which on NPG 2.65.4 a
    token created by the UI can never hold (``POST /api/v1/api-tokens`` accepts
    only ``*`` or the 15 legacy resource scopes, and token checks are exact
    matches). So a scoped token lands here as a 403 and the caller falls back to
    :func:`_from_self`.
    """
    try:
        payload = client.get(path)
    except Exception as exc:  # 403 no apitoken:read, timeout, transport error
        return Introspection(reason=f"{path} failed: {exc}")
    rows = _token_rows(payload)
    if rows is None:
        return Introspection(reason=f"{path} returned an unexpected shape")
    row, reason = match_token_row(rows, token)
    if row is None:
        return Introspection(reason=reason)
    prefix = str(row.get("token_prefix") or "")
    stored = row.get("permissions")
    if not isinstance(stored, list) or not stored:
        return Introspection(
            token_prefix=prefix, reason=f"{path} row carries no permissions array"
        )
    cleaned = _usable_permissions(stored)
    if not cleaned:
        return Introspection(
            token_prefix=prefix,
            reason=f"{path} row carries no usable permissions",
        )
    return Introspection(stored=cleaned, source=path, token_prefix=prefix)


def _from_self(client, path: str) -> Introspection:
    """Fallback: ask ``GET /api/v1/auth/me`` who the token is and what it may do.

    ``/auth/me`` is a self-service route (no permission needed), and for an API
    token caller upstream returns ``effective_permissions`` = the owner role's
    expanded permissions intersected with the token's own scopes — exactly the
    set ``CanToken`` enforces on every request. It is therefore the most
    accurate grant available, and it works for scoped tokens that cannot read
    the token list. A superuser token reports ``is_superuser: true`` and the
    full area catalogue; that is normalised to ``["*"]``.
    """
    try:
        payload = client.get(path)
    except Exception as exc:
        return Introspection(reason=f"{path} failed: {exc}")
    if not isinstance(payload, dict):
        return Introspection(reason=f"{path} returned an unexpected shape")
    if payload.get("is_superuser") is True:
        return Introspection(stored=("*",), source=path)
    stored = payload.get("effective_permissions")
    if not isinstance(stored, list) or not stored:
        return Introspection(reason=f"{path} carries no effective_permissions array")
    cleaned = _usable_permissions(stored)
    if not cleaned:
        return Introspection(reason=f"{path} carries no usable effective_permissions")
    return Introspection(stored=cleaned, source=path)


def introspect(
    client,
    token: str,
    list_path: str = "/api/v1/api-tokens",
    me_path: str = "/api/v1/auth/me",
) -> Introspection:
    """Resolve the configured token's grant. Never raises.

    Tries the token-row introspection first (it reports the row's own
    ``permissions`` and its displayable prefix), then the self endpoint. Returns
    an :class:`Introspection` whose ``stored`` is None when both failed — the
    caller must then fail open, with ``reason`` explaining both attempts.
    """
    if not token:
        return Introspection(reason="NPG_API_TOKEN is not set")
    primary = _from_token_row(client, token, list_path)
    if primary.ok:
        return primary
    fallback = _from_self(client, me_path)
    if fallback.ok:
        return Introspection(
            stored=fallback.stored,
            source=fallback.source,
            token_prefix=primary.token_prefix,
            reason="",
        )
    return Introspection(reason=f"{primary.reason}; {fallback.reason}")


def apply(
    mcp,
    enabled: bool | None = None,
    token: str | None = None,
    client=None,
) -> FilterState:
    """Narrow ``mcp``'s manifest to what the configured token may call.

    Must run AFTER ``toolsets.configure_toolset`` so the tier filter has already
    removed its tools: the surviving set is ``tier ∩ grant`` by construction.
    Must run BEFORE the transport starts (removing a tool makes it unknown to
    ``tools/list`` and ``tools/call``).

    Never raises and never hides anything on failure — see the module docstring
    for the fail-open contract. Returns the recorded :class:`FilterState`.
    """
    global _STATE
    is_enabled = resolve_enabled() if enabled is None else enabled
    snapshot = FilterState(enabled=is_enabled)
    if not is_enabled:
        logger.debug("%s is off — full manifest served", FILTER_ENV)
        _STATE = snapshot
        return snapshot

    try:
        names = {tool.name for tool in mcp._tool_manager.list_tools()}
    except Exception as exc:  # pragma: no cover - defensive
        snapshot.reason = f"cannot list tools: {exc}"
        logger.warning("scope filter: %s — exposing every tool", snapshot.reason)
        _STATE = snapshot
        return snapshot

    snapshot.manifest_before = len(names)
    snapshot.manifest_after = len(names)
    snapshot.unmapped_tools = tuple(sorted(unmapped_tools(names)))

    api_token = (
        token if token is not None else os.environ.get("NPG_API_TOKEN", "")
    ).strip()
    found: Introspection
    try:
        if client is None:
            client = client_mod.get_singleton(api_token) if api_token else None
        if client is None:
            found = Introspection(reason="NPG_API_TOKEN is not set")
        else:
            found = introspect(client, api_token)
    except Exception as exc:  # pragma: no cover - defensive
        found = Introspection(reason=f"introspection failed: {exc}")

    snapshot.reason = found.reason
    snapshot.token_prefix = found.token_prefix
    snapshot.source = found.source
    snapshot.stored_permissions = found.stored or ()
    if found.stored is None:
        logger.warning(
            "scope filter: failing OPEN (exposing all %d tools) — %s",
            len(names),
            found.reason,
        )
        _STATE = snapshot
        return snapshot

    snapshot.granted_scopes = tuple(sorted(expand_permissions(found.stored)))
    keep = select_exposed(names, found.stored)
    removed_names: list[str] = []
    for name in sorted(names - keep):
        try:
            mcp.remove_tool(name)
            removed_names.append(name)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("scope filter: could not remove %r: %s", name, exc)
    snapshot.applied = True
    snapshot.hidden_tools = tuple(removed_names)
    snapshot.manifest_after = len(names) - len(removed_names)
    logger.info(
        "scope filter: token %s (%s) holds %d permission(s) — exposing %d of %d "
        "tools (%d hidden by scope, %d unannotated kept)",
        found.token_prefix or "<unknown>",
        found.source,
        len(found.stored),
        snapshot.manifest_after,
        len(names),
        len(removed_names),
        len(snapshot.unmapped_tools),
    )
    _STATE = snapshot
    return snapshot

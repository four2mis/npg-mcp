"""Unit tests for the opt-in scope-aware tool filter (NPG_TOOL_SCOPE_FILTER).

No network and no mutations: the client handed to ``scopefilter.apply`` is a
path-aware fake, and the FastMCP instance is built from a handful of real
registered tools.

The contract under test (see ``npg_mcp/scopefilter.py``):

* OFF (the default) changes nothing — no introspection request, same manifest;
* ``*`` grants every permission, an ``area:*`` family wildcard grants its
  family, and everything else is matched EXACTLY — no legacy→area expansion and
  no verb hierarchy, because that is what ``APIToken.HasPermission`` does (the
  implication table is for roles only). Verified live on NPG 2.65.4: a
  ``read_only`` token reaches exactly proxy/certificate/waf/logs/settings/
  backup read and 403s on redirect/access/authprovider/dnsprovider/ddns/audit/
  dashboard/user/role;
* the token row is found by prefix match; when the row cannot be read (a scoped
  token can never hold ``apitoken:read``) the ``/auth/me`` self endpoint is used
  instead, and both failing fails OPEN with a reason;
* exposure is ``tier membership ∩ granted scopes`` — the tier filter runs first,
  so the filter can only ever narrow it;
* the tools-list clients see reflects the filter and unannotated tools are never
  hidden;
* ``npg_get_stack_features`` reports ``hidden_by_scope`` when filtering is on
  and ``None`` when it is off.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

import npg_mcp.main as main_mod
import npg_mcp.scopefilter as scopefilter
import npg_mcp.toolsets as toolsets
from npg_mcp.client import NPGError
from npg_mcp.permission_map import TOOL_PERMISSIONS

TOKEN = "ng_1bee0df4deadbeefcafe"
LIST_PATH = "/api/v1/api-tokens"
ME_PATH = "/api/v1/auth/me"
READ_ONLY = [
    "proxy:read",
    "certificate:read",
    "waf:read",
    "logs:read",
    "settings:read",
    "backup:read",
]

# A representative slice of the real surface: permission-free, read, write,
# destructive, a reviewed permission-free override, and a read-modify-write
# tool that needs both the read and the write permission.
SAMPLE_TOOLS = [
    "npg_get_auth_status",  # permission-free (public route)
    "npg_list_proxy_hosts",  # proxy:read
    "npg_create_proxy_host",  # proxy:write
    "npg_delete_proxy_host",  # proxy:delete
    "npg_list_waf_rules",  # waf:read
    "npg_update_proxy_host_cloud_blocking",  # proxy:read + proxy:write
    "npg_get_stack_features",  # reviewed override: permission-free
]


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Every test starts with the filter off and no env leakage."""
    monkeypatch.delenv(scopefilter.FILTER_ENV, raising=False)
    monkeypatch.delenv("NPG_API_TOKEN", raising=False)
    monkeypatch.setattr(scopefilter, "_STATE", scopefilter.FilterState())
    yield
    monkeypatch.setattr(scopefilter, "_STATE", scopefilter.FilterState())


class FakeClient:
    """Path-aware NPGClient stand-in.

    ``routes`` maps a path to either a payload or an Exception to raise. An
    unknown path raises ``AssertionError`` so an unexpected request fails loudly
    instead of silently shaping the result.
    """

    def __init__(self, routes: dict[str, object] | None = None):
        self.routes = routes if routes is not None else {}
        self.calls: list[str] = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path not in self.routes:
            raise AssertionError(f"unexpected GET {path}")
        value = self.routes[path]
        if isinstance(value, Exception):
            raise value
        return value


def token_payload(permissions, prefix="ng_1bee0df4"):
    """Build a ``GET /api/v1/api-tokens`` bare-array response."""
    return [
        {
            "id": "cf55fc0a-db2f-402d-9c07-3602ebae4bd3",
            "name": "mcp-test",
            "token_prefix": prefix,
            "permissions": permissions,
        }
    ]


def me_payload(permissions, superuser=False):
    """Build a ``GET /api/v1/auth/me`` response for a token caller."""
    return {
        "role": "admin",
        "is_superuser": superuser,
        "effective_permissions": permissions,
    }


def row_client(permissions):
    """Client whose token list answers with one matching row."""
    return FakeClient(routes={LIST_PATH: token_payload(permissions)})


def build_mcp(names=None) -> FastMCP:
    """Register throwaway tools so the filter has a real manifest to narrow."""
    mcp = FastMCP("scope-filter-test")
    for name in names if names is not None else SAMPLE_TOOLS:
        def _make(tool_name=name):
            async def tool() -> dict:
                return {"success": True}

            tool.__name__ = tool_name
            return tool

        mcp.tool(name=name, description="test tool")(_make())
    return mcp


def listed(mcp) -> set[str]:
    return {tool.name for tool in mcp._tool_manager.list_tools()}


def run_apply(mcp, client, enabled=True, token=TOKEN) -> scopefilter.FilterState:
    return scopefilter.apply(mcp, enabled=enabled, token=token, client=client)


# ── default OFF ────────────────────────────────────────────────────────


def test_off_by_default_leaves_manifest_untouched():
    assert scopefilter.resolve_enabled(None) is False  # env unset
    for value in ("", "0", "false", "no", "FALSE"):
        assert scopefilter.resolve_enabled(value) is False
    for value in ("1", "true", "YES", "on", "enabled"):
        assert scopefilter.resolve_enabled(value) is True


def test_disabled_filter_never_calls_the_api_and_keeps_every_tool():
    mcp = build_mcp()
    before = listed(mcp)
    client = row_client(["proxy:read"])
    state = run_apply(mcp, client, enabled=False)

    assert client.calls == []  # no introspection at all
    assert listed(mcp) == before
    assert state.enabled is False
    assert state.applied is False
    assert scopefilter.hidden_by_scope() is None


# ── permission matching (mirrors APIToken.HasPermission) ───────────────


def test_star_grants_every_permission():
    assert scopefilter.has_permission(("*",), "waf:write")
    assert set(scopefilter.ALL_PERMISSIONS) <= scopefilter.expand_permissions(["*"])
    assert scopefilter.select_exposed(set(TOOL_PERMISSIONS), ("*",)) == set(
        TOOL_PERMISSIONS
    )


def test_star_keeps_the_manifest_identical():
    mcp = build_mcp()
    before = listed(mcp)
    state = run_apply(mcp, row_client(["*"]))

    assert listed(mcp) == before
    assert state.applied is True
    assert state.hidden_tools == ()
    assert state.manifest_after == state.manifest_before == len(before)
    assert state.source == LIST_PATH


def test_matching_is_exact_with_no_role_expansion():
    """Legacy scopes do NOT widen into other areas (verified against 2.65.4).

    A token holding ``proxy:read`` + ``settings:read`` answers 403 on
    ``/api/v1/redirect-hosts`` (redirect:read) and on ``/api/v1/api-tokens``
    (apitoken:read), so the filter must not pretend otherwise.
    """
    held = ("proxy:read", "settings:read")
    assert scopefilter.has_permission(held, "proxy:read")
    assert scopefilter.has_permission(held, "settings:read")
    for not_granted in (
        "proxy:write",
        "proxy:delete",
        "redirect:read",
        "access:read",
        "authprovider:read",
        "dashboard:read",
        "audit:read",
        "ddns:read",
        "apitoken:read",
        "logs:read",
        "user:write",
    ):
        assert not scopefilter.has_permission(held, not_granted), not_granted


def test_family_wildcard_grants_its_family_only():
    held = ("proxy:*",)
    for granted in ("proxy:read", "proxy:write", "proxy:delete"):
        assert scopefilter.has_permission(held, granted)
    for not_granted in ("waf:read", "redirect:read", "proxying:read"):
        assert not scopefilter.has_permission(held, not_granted), not_granted
    expanded = scopefilter.expand_permissions(["proxy:*"])
    assert {"proxy:read", "proxy:write", "proxy:delete"} <= expanded
    assert "waf:read" not in expanded


def test_malformed_permission_values_never_grant_anything():
    assert not scopefilter.has_permission(("", "nonsense", "proxy"), "proxy:read")
    assert not scopefilter.has_permission((), "proxy:read")


# ── introspection: token row first, self endpoint second ───────────────


def test_prefix_match_success_reads_that_row_only():
    client = FakeClient(
        routes={
            LIST_PATH: [
                {"token_prefix": "ng_deadbeef", "permissions": ["*"]},
                {"token_prefix": "ng_1bee0df4", "permissions": ["proxy:read"]},
            ]
        }
    )
    found = scopefilter.introspect(client, TOKEN)
    assert found.ok
    assert found.stored == ("proxy:read",)
    assert found.token_prefix == "ng_1bee0df4"
    assert found.source == LIST_PATH
    assert client.calls == [LIST_PATH]  # no fallback needed


def test_scoped_token_falls_back_to_the_self_endpoint():
    """The real-world path: the token list is 403 for a scoped token."""
    client = FakeClient(
        routes={
            LIST_PATH: NPGError("NPG API returned HTTP 403", "required apitoken:read"),
            ME_PATH: me_payload(READ_ONLY),
        }
    )
    found = scopefilter.introspect(client, TOKEN)
    assert found.ok
    assert found.stored == tuple(READ_ONLY)
    assert found.source == ME_PATH
    assert client.calls == [LIST_PATH, ME_PATH]


def test_superuser_token_from_the_self_endpoint_is_star():
    client = FakeClient(
        routes={
            LIST_PATH: NPGError("NPG API returned HTTP 403"),
            ME_PATH: me_payload([], superuser=True),
        }
    )
    found = scopefilter.introspect(client, TOKEN)
    assert found.stored == ("*",)


def test_enveloped_token_list_shape_is_accepted():
    client = FakeClient(routes={LIST_PATH: {"data": token_payload(["waf:read"])}})
    found = scopefilter.introspect(client, TOKEN)
    assert found.ok
    assert found.stored == ("waf:read",)


def test_self_endpoint_is_not_used_when_the_row_was_read():
    client = FakeClient(
        routes={
            LIST_PATH: token_payload(["waf:read"]),
            ME_PATH: me_payload(["*"], superuser=True),
        }
    )
    found = scopefilter.introspect(client, TOKEN)
    assert found.stored == ("waf:read",)
    assert client.calls == [LIST_PATH]


# ── fail-open on every introspection failure ───────────────────────────


@pytest.mark.parametrize(
    "routes, reason_fragment",
    [
        # both endpoints refuse (no apitoken:read, no self route)
        (
            {
                LIST_PATH: NPGError("NPG API returned HTTP 403"),
                ME_PATH: NPGError("NPG API returned HTTP 403"),
            },
            "403",
        ),
        # transport failures on both
        (
            {
                LIST_PATH: TimeoutError("timed out"),
                ME_PATH: TimeoutError("timed out"),
            },
            "timed out",
        ),
        # unparseable token list + unparseable self payload
        (
            {LIST_PATH: {"unexpected": "shape"}, ME_PATH: ["not", "a", "dict"]},
            "unexpected",
        ),
        # no row matches the configured token
        (
            {
                LIST_PATH: token_payload(["*"], prefix="ng_ffffffff"),
                ME_PATH: NPGError("boom"),
            },
            "no API-token row matches",
        ),
        # empty permissions array on the row, nothing usable from self either
        (
            {LIST_PATH: token_payload([]), ME_PATH: me_payload([])},
            "permissions array",
        ),
        # garbage permission entries
        (
            {LIST_PATH: token_payload([""]), ME_PATH: me_payload(["", "x"])},
            "usable",
        ),
    ],
)
def test_introspection_failures_fail_open(routes, reason_fragment):
    mcp = build_mcp()
    before = listed(mcp)
    state = run_apply(mcp, FakeClient(routes=routes))

    assert listed(mcp) == before, "fail-open must not hide anything"
    assert state.applied is False
    assert reason_fragment in state.reason
    report = scopefilter.hidden_by_scope()
    assert report is not None and report["applied"] is False


def test_ambiguous_prefix_fails_open_when_the_fallback_also_fails():
    routes = {
        LIST_PATH: [
            {"token_prefix": "ng_1bee0df4", "permissions": ["*"]},
            {"token_prefix": "ng_1bee0df4", "permissions": ["proxy:read"]},
        ],
        ME_PATH: NPGError("NPG API returned HTTP 403"),
    }
    mcp = build_mcp()
    before = listed(mcp)
    state = run_apply(mcp, FakeClient(routes=routes))

    assert listed(mcp) == before
    assert state.applied is False
    assert "ambiguous" in state.reason


def test_unset_token_fails_open_without_any_request():
    mcp = build_mcp()
    before = listed(mcp)
    client = FakeClient()
    state = run_apply(mcp, client, token="")

    assert listed(mcp) == before
    assert state.applied is False
    assert "NPG_API_TOKEN is not set" in state.reason
    assert client.calls == []


# ── filtering behaviour ────────────────────────────────────────────────


def _read_only_client():
    return FakeClient(
        routes={LIST_PATH: NPGError("403"), ME_PATH: me_payload(READ_ONLY)}
    )


def test_scope_filter_hides_uncovered_tools_and_keeps_the_rest():
    mcp = build_mcp()
    state = run_apply(mcp, _read_only_client())

    remaining = listed(mcp)
    assert state.applied is True
    assert "npg_list_proxy_hosts" in remaining  # proxy:read
    assert "npg_list_waf_rules" in remaining  # waf:read
    assert "npg_create_proxy_host" not in remaining  # proxy:write
    assert "npg_delete_proxy_host" not in remaining  # proxy:delete
    # permission-free tools are never hidden
    assert "npg_get_auth_status" in remaining
    assert "npg_get_stack_features" in remaining
    assert "npg_create_proxy_host" in state.hidden_tools
    assert state.manifest_after == len(remaining)


def test_read_modify_write_tool_needs_both_permissions():
    """A GET-then-PUT tool needs the read AND the write permission."""
    mcp = build_mcp()
    run_apply(mcp, row_client(["proxy:write"]))
    assert "npg_update_proxy_host_cloud_blocking" not in listed(mcp)

    mcp = build_mcp()
    run_apply(mcp, row_client(["proxy:read"]))
    assert "npg_update_proxy_host_cloud_blocking" not in listed(mcp)

    mcp = build_mcp()
    run_apply(mcp, row_client(["proxy:read", "proxy:write"]))
    assert "npg_update_proxy_host_cloud_blocking" in listed(mcp)

    # a family wildcard covers both
    mcp = build_mcp()
    run_apply(mcp, row_client(["proxy:*"]))
    assert "npg_update_proxy_host_cloud_blocking" in listed(mcp)


def test_unannotated_tool_is_always_exposed():
    mcp = build_mcp(SAMPLE_TOOLS + ["npg_brand_new_tool"])
    assert "npg_brand_new_tool" not in TOOL_PERMISSIONS  # premise

    state = run_apply(mcp, row_client(["proxy:read"]))
    assert "npg_brand_new_tool" in listed(mcp)
    assert state.unmapped_tools == ("npg_brand_new_tool",)


def test_tier_intersection_is_applied_before_the_scope_filter():
    """exposed = tier membership ∩ granted — the filter can only narrow."""
    mcp = build_mcp()
    toolsets.configure_toolset(mcp, "read")
    tier_names = listed(mcp)
    assert "npg_create_proxy_host" not in tier_names  # removed by the tier

    state = run_apply(mcp, row_client(["*"]))
    assert listed(mcp) == tier_names
    assert state.hidden_tools == ()
    assert state.manifest_before == len(tier_names)

    # ... and a narrow grant is a strict subset of the tier
    mcp = build_mcp()
    toolsets.configure_toolset(mcp, "read")
    run_apply(mcp, row_client(["waf:read"]))
    assert listed(mcp) == {
        "npg_get_auth_status",
        "npg_list_waf_rules",
        "npg_get_stack_features",
    }


def test_filter_is_idempotent():
    mcp = build_mcp()
    run_apply(mcp, row_client(["proxy:read"]))
    once = listed(mcp)
    run_apply(mcp, row_client(["proxy:read"]))
    assert listed(mcp) == once


# ── stack-features reporting ───────────────────────────────────────────


def test_hidden_by_scope_reports_the_snapshot_when_on():
    mcp = build_mcp()
    run_apply(mcp, row_client(READ_ONLY))
    report = scopefilter.hidden_by_scope()

    assert report is not None
    assert report["enabled"] is True
    assert report["applied"] is True
    assert report["snapshot"] == "boot"
    assert report["source"] == LIST_PATH
    assert report["token_prefix"] == "ng_1bee0df4"
    assert report["stored_permissions"] == READ_ONLY
    assert report["hidden_count"] == len(report["hidden_tools"])
    assert "npg_create_proxy_host" in report["hidden_tools"]
    assert report["exposed_count"] == report["manifest_before"] - report["hidden_count"]
    assert report["unmapped_tool_count"] == 0


def test_stack_features_carries_hidden_by_scope(monkeypatch):
    """The tool reports the filter state; None when the filter is off."""
    monkeypatch.setattr(main_mod, "_get_client", lambda: FakeStackClient())

    off = asyncio.run(main_mod.npg_get_stack_features())
    assert "hidden_by_scope" in off["data"]
    assert off["data"]["hidden_by_scope"] is None
    assert off["data"]["families_probed"] == 10  # the field is not a family

    mcp = build_mcp()
    run_apply(mcp, row_client(["proxy:read"]))
    on = asyncio.run(main_mod.npg_get_stack_features())
    hidden = on["data"]["hidden_by_scope"]
    assert hidden is not None and hidden["applied"] is True
    assert "npg_create_proxy_host" in hidden["hidden_tools"]


class FakeStackClient:
    """Serves the ten stack-feature probes with empty-ish payloads."""

    def get(self, path, params=None):
        if path in ("/api/v1/sso-providers", "/api/v1/notification-channels"):
            return []
        return {}


# ── generated map invariants ───────────────────────────────────────────


def test_permission_map_covers_exactly_the_registered_tools():
    """A tool added to main.py without regenerating the map fails here."""
    registered = toolsets._discover_tool_names()
    assert registered, "no tools discovered from main.py"
    missing = sorted(registered - set(TOOL_PERMISSIONS))
    stale = sorted(set(TOOL_PERMISSIONS) - registered)
    assert missing == [], f"tools missing from permission_map.py: {missing}"
    assert stale == [], f"permission_map.py names unknown tools: {stale}"


def test_permission_map_values_are_known_permissions():
    known = set(scopefilter.ALL_PERMISSIONS) | set(scopefilter.LEGACY_SCOPES)
    unknown = {
        name: [p for p in required if p not in known]
        for name, required in TOOL_PERMISSIONS.items()
        if any(p not in known for p in required)
    }
    assert unknown == {}

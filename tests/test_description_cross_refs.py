"""Guard for the deduplicated tool descriptions.

Sibling tools no longer repeat a shared warning/validation block. Each block is
owned by one canonical tool; its siblings point at it with a short
cross-reference ("... same as npg_X") and keep only their own endpoint-specific
behaviour.

This module pins that contract so the duplicated prose cannot creep back:

* every ``npg_*`` name used inside any description resolves to a registered
  tool (a cross-reference must never dangle),
* for each ``SHARED_BLOCKS`` entry the canonical tool still carries the block,
* the siblings name the canonical tool and do NOT repeat the block.

Pure in-process tests — the descriptions come from the registered FastMCP
tools, i.e. exactly what a client sees in ``tools/list``. No network.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

import pytest

from npg_mcp import main as main_mod

# A tool reference is a whole ``npg_...`` token: a trailing "/" or "-" means the
# description is abbreviating a family ("npg_get/update_proxy_host_uri_block"),
# not naming one tool.
TOOL_REF = re.compile(r"npg_[a-z0-9_]*[a-z0-9](?![a-z0-9_/-])")


@dataclass(frozen=True)
class SharedBlock:
    """One warning/validation block that only the canonical tool may spell out."""

    name: str
    canonical: str
    block: str
    siblings: tuple[str, ...] = field(default_factory=tuple)


SHARED_BLOCKS: tuple[SharedBlock, ...] = (
    SharedBlock(
        name="confirm-dns re-lookup and 400/403/409 handling",
        canonical="npg_confirm_trusted_dns",
        block=(
            "403 lacks write permission on another list using the domain; "
            "409 lookup_unavailable/observation_changed/"
            "nginx_reload_rejected."
        ),
        siblings=(
            "npg_confirm_proxy_host_dns",
            "npg_confirm_access_list_dns",
            "npg_confirm_global_uri_block_dns",
            "npg_confirm_global_geo_dns",
            "npg_confirm_global_rate_limit_dns",
        ),
    ),
    SharedBlock(
        name="paginated list paging/metadata/zero-arg",
        canonical="npg_list_redirect_hosts",
        block="Paginated responses include metadata. Zero-arg returns the full list.",
        siblings=(
            "npg_list_certificates",
            "npg_list_access_lists",
            "npg_list_banned_ips",
            "npg_list_backups",
            "npg_list_ddns_records",
            "npg_list_filter_subscriptions",
        ),
    ),
    SharedBlock(
        name="MCP-side limit/offset slicing",
        canonical="npg_list_users",
        block="MCP-side slice of the full list (upstream ignores paging query params).",
        siblings=(
            "npg_list_api_tokens",
            "npg_list_roles",
            "npg_list_sso_providers",
            "npg_list_notification_channels",
        ),
    ),
    SharedBlock(
        name="log autocomplete q/limit filtering",
        canonical="npg_get_log_autocomplete_hosts",
        block="Omitted params = unfiltered full list, same as before.",
        siblings=(
            "npg_get_log_autocomplete_ips",
            "npg_get_log_autocomplete_uris",
            "npg_get_log_autocomplete_user_agents",
        ),
    ),
    SharedBlock(
        name="bulk per-item failure isolation",
        canonical="npg_bulk_apply_certificate",
        block="one failure does not abort the batch",
        siblings=(
            "npg_bulk_delete_proxy_hosts",
            "npg_bulk_renew_certificates",
        ),
    ),
    SharedBlock(
        name="strict kwargs validation",
        canonical="npg_update_settings",
        block="Unknown fields rejected unless strict=false.",
        siblings=(
            "npg_update_dns_provider",
            "npg_update_cloud_provider",
            "npg_update_exploit_rule",
            "npg_update_log_settings",
            "npg_update_api_token",
            "npg_update_cloudflare_tunnel",
            "npg_update_global_fail2ban",
        ),
    ),
    SharedBlock(
        name="global partial-update omitted-field semantics",
        canonical="npg_update_global_bot_filter",
        block="only provided fields are changed; omitted fields are left as-is",
        siblings=(
            "npg_update_global_cloud_providers",
            "npg_update_global_uri_block",
        ),
    ),
)


@pytest.fixture(scope="module")
def descriptions() -> dict[str, str]:
    """Served description per registered tool (what tools/list returns)."""
    tools = asyncio.run(main_mod.mcp.list_tools())
    return {t.name: (t.description or "") for t in tools}


class TestToolReferences:
    def test_no_dangling_tool_references(self, descriptions: dict[str, str]) -> None:
        dangling = []
        for name, desc in descriptions.items():
            for ref in sorted(set(TOOL_REF.findall(desc))):
                if ref not in descriptions:
                    dangling.append(f"{name} -> {ref}")
        assert not dangling, "descriptions reference unknown tools: " + str(dangling)


class TestSharedBlocks:
    @pytest.mark.parametrize("shared", SHARED_BLOCKS, ids=lambda s: s.name)
    def test_canonical_tool_owns_the_block(
        self, shared: SharedBlock, descriptions: dict[str, str]
    ) -> None:
        assert shared.canonical in descriptions
        assert shared.block in descriptions[shared.canonical], (
            f"{shared.canonical} must keep the full '{shared.name}' block"
        )

    @pytest.mark.parametrize("shared", SHARED_BLOCKS, ids=lambda s: s.name)
    def test_siblings_cross_reference_instead_of_repeating(
        self, shared: SharedBlock, descriptions: dict[str, str]
    ) -> None:
        problems = []
        for sibling in shared.siblings:
            desc = descriptions.get(sibling)
            if desc is None:
                problems.append(f"{sibling}: not a registered tool")
                continue
            if shared.canonical not in desc:
                problems.append(f"{sibling}: does not name {shared.canonical}")
            if shared.block in desc:
                problems.append(f"{sibling}: repeats the '{shared.name}' block")
        assert not problems, "; ".join(problems)

    @pytest.mark.parametrize("shared", SHARED_BLOCKS, ids=lambda s: s.name)
    def test_no_unlisted_tool_repeats_the_block(
        self, shared: SharedBlock, descriptions: dict[str, str]
    ) -> None:
        allowed = {shared.canonical}
        repeats = [
            name
            for name, desc in descriptions.items()
            if shared.block in desc and name not in allowed
        ]
        assert not repeats, (
            f"block '{shared.name}' repeated in {repeats} — cross-reference "
            f"{shared.canonical} instead"
        )

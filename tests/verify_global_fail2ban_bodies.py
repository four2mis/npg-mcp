#!/usr/bin/env python3
"""Body-construction harness for the new global fail2ban tools (t_ee4fd5ad).

Monkeypatches npg_mcp.main._get_client with a fake client that records every
PUT/GET call, then asserts npg_update_global_fail2ban forwards the kwargs dict
verbatim (partial update semantics) and rejects unknown fields via the
upstream_models whitelist. No network, no writes.
"""
import asyncio
import os
import sys

REPO_DIR = os.environ.get("NPG_MCP_REPO", "/home/four2mis/workspace/npg-mcp")
sys.path.insert(0, REPO_DIR)

import npg_mcp.main as main  # noqa: E402

recorded = []


class FakeClient:
    def get(self, path):
        recorded.append(("GET", path, None))
        return {"id": "x", "enabled": False, "max_retries": 5, "find_time": 600,
                "ban_time": 3600, "fail_codes": "400,444", "action": "log"}

    def put(self, path, body, params=None):
        recorded.append(("PUT", path, body))
        return {"ok": True}


main._get_client = lambda: FakeClient()
fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


async def run():
    # GET tool hits the right endpoint
    recorded.clear()
    r = await main.npg_get_global_fail2ban()
    check("get_global_fail2ban: GET endpoint",
          recorded[0][:2] == ("GET", "/api/v1/settings/global-fail2ban") and r.get("success") is True,
          recorded[0])

    # partial update: full field set forwarded verbatim
    recorded.clear()
    r = await main.npg_update_global_fail2ban(kwargs={"enabled": False, "max_retries": 3,
                                                      "find_time": 120, "ban_time": 0,
                                                      "fail_codes": "400,444", "action": "log"})
    check("update_global_fail2ban: full body verbatim",
          recorded[0] == ("PUT", "/api/v1/settings/global-fail2ban",
                          {"enabled": False, "max_retries": 3, "find_time": 120,
                           "ban_time": 0, "fail_codes": "400,444", "action": "log"})
          and r.get("success") is True, recorded[0])

    # partial update: single field only — omitted fields NOT sent (no zero-value wipe)
    recorded.clear()
    await main.npg_update_global_fail2ban(kwargs={"action": "notify"})
    check("update_global_fail2ban: single-field body", recorded[0][2] == {"action": "notify"}, recorded[0])

    # empty kwargs -> PUT {} (upstream accepts, no-op partial)
    recorded.clear()
    await main.npg_update_global_fail2ban(kwargs={})
    check("update_global_fail2ban: empty body {} allowed", recorded[0][2] == {}, recorded[0])

    # unknown field rejected client-side (whitelist enforcement)
    r = await main.npg_update_global_fail2ban(kwargs={"difficulty": 5})
    check("update_global_fail2ban: unknown field rejected", r.get("success") is False and "difficulty" in str(r.get("error")), r)

    # strict=False bypasses validation
    recorded.clear()
    await main.npg_update_global_fail2ban(kwargs={"difficulty": 5}, strict=False)
    check("update_global_fail2ban: strict=False bypass", recorded[0][2] == {"difficulty": 5}, recorded[0])

    # whitelist contains exactly the 6 upstream pointer fields
    from npg_mcp.upstream_models import TOOL_KWARGS_WHITELIST
    check("upstream_models frozenset exact",
          TOOL_KWARGS_WHITELIST.get("npg_update_global_fail2ban") ==
          frozenset({"enabled", "max_retries", "find_time", "ban_time", "fail_codes", "action"}),
          TOOL_KWARGS_WHITELIST.get("npg_update_global_fail2ban"))


asyncio.run(run())
print(f"\n{'ALL CHECKS PASSED' if not fails else f'FAILED: {fails}'}")
sys.exit(1 if fails else 0)
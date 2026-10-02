"""Unit tests for npg_match_filter_subscriptions.

Verifies, without any network access:
* ip-only / user_agent-only / both-params calls forward values verbatim as
  GET query params to /api/v1/filter-subscriptions/match,
* calling with neither param surfaces a client-side error (success: False),
* the tool is registered (297 tools total) and does NOT join the read tier
  (it does not match ^npg_(get|list|view|download|check|detect)).

Monkeypatches npg_mcp.main._get_client with a recording fake so the tool's
real code path runs end to end.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod


class _RecordingClient:
    """Fake NPGClient that records the last GET call."""

    def __init__(self):
        self.calls = []

    def get(self, path, params=None, redirect_ok=False):
        self.calls.append(("GET", path, params))
        return {"ip_matches": [], "user_agent_matches": []}


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def test_ip_only_forwards_ip_param(recording):
    result = _run(main_mod.npg_match_filter_subscriptions(ip="1.2.3.4"))
    assert result == {
        "success": True,
        "data": {"ip_matches": [], "user_agent_matches": []},
    }
    assert recording.calls == [
        ("GET", "/api/v1/filter-subscriptions/match", {"ip": "1.2.3.4"})
    ]


def test_user_agent_only_forwards_user_agent_param(recording):
    result = _run(
        main_mod.npg_match_filter_subscriptions(user_agent="curl/8.0")
    )
    assert result["success"] is True
    assert recording.calls == [
        ("GET", "/api/v1/filter-subscriptions/match", {"user_agent": "curl/8.0"})
    ]


def test_both_params_forwarded_verbatim(recording):
    result = _run(
        main_mod.npg_match_filter_subscriptions(
            ip="2001:db8::1", user_agent="Mozilla/5.0 (X11; Linux x86_64)"
        )
    )
    assert result["success"] is True
    assert recording.calls == [
        (
            "GET",
            "/api/v1/filter-subscriptions/match",
            {"ip": "2001:db8::1", "user_agent": "Mozilla/5.0 (X11; Linux x86_64)"},
        )
    ]


def test_neither_param_is_a_client_side_error(recording):
    result = _run(main_mod.npg_match_filter_subscriptions())
    assert result["success"] is False
    assert "ip or user_agent is required" in result["error"]
    # No HTTP call was made.
    assert recording.calls == []


def test_invalid_ip_passthrough_and_upstream_error(monkeypatch):
    """Non-IP strings are passed verbatim (upstream validates, not the MCP)."""

    class _Upstream400:
        def get(self, path, params=None, redirect_ok=False):
            raise RuntimeError("NPG API returned HTTP 400")

    monkeypatch.setattr(main_mod, "_get_client", lambda: _Upstream400())
    result = _run(main_mod.npg_match_filter_subscriptions(ip="not-an-ip"))
    assert result["success"] is False
    assert "HTTP 400" in result["error"]


def test_tool_registered_and_not_in_read_tier():
    names = set(main_mod.toolsets._discover_tool_names())
    assert "npg_match_filter_subscriptions" in names
    assert (
        "npg_match_filter_subscriptions"
        not in main_mod.toolsets.tier_allowed(names, "read")
    )
    assert (
        "npg_match_filter_subscriptions"
        in main_mod.toolsets.tier_allowed(names, "full")
    )
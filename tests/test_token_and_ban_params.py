"""Unit tests for the API-token scoping / host-scoped-ban parameters.

Covers the optional parameters added to three existing tools, with no network
access (recording fake client). Every added field must be omitted from the
request body unless the caller supplies it, so bare calls stay byte-identical
to the previous release:

* ``npg_create_api_token`` — ``allowed_ips`` (IP/CIDR allowlist; empty or
  omitted = no IP restriction) and ``rate_limit`` (per-token override; must be
  a positive integer, because 0 means "no limit" upstream and a typo must not
  silently disable throttling on a machine credential).
* ``npg_ban_ip`` — ``proxy_host_id`` scopes the ban to one host. The key must
  be ABSENT for a global ban: an empty string is not "global" to the API, it
  fails the UUID parse, so ``None`` and blank input both omit the field and a
  real id is sent raw (``_id_str``, never URL-encoded).
* ``npg_revoke_api_token`` — ``reason`` is an optional audit note; omitting it
  must send no body at all (the endpoint has no required body).

The description assertions pin the same-commit rule: a signature change whose
description still omits the new parameters fails the publish workflow's
validate gate, so the names are asserted right here.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

import npg_mcp.main as main_mod

HOST = "11111111-1111-1111-1111-111111111111"
TOKEN = "22222222-2222-2222-2222-222222222222"


class _RecordingClient:
    """Fake NPGClient recording every (method, path, body, params) call."""

    def __init__(self, post_response=None):
        self.calls: list[tuple] = []
        self._post_response = (
            post_response if post_response is not None else {"ok": True}
        )

    def get(self, path, params=None):
        self.calls.append(("GET", path, None, params))
        return {}

    def post(self, path, body=None, params=None):
        self.calls.append(("POST", path, body, params))
        return self._post_response

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        return {"ok": True}

    def delete(self, path, params=None):
        self.calls.append(("DELETE", path, None, params))
        return None


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _single_post(recording):
    posts = [c for c in recording.calls if c[0] == "POST"]
    assert len(posts) == 1, f"expected exactly one POST, got {recording.calls}"
    return posts[0]


def _description(tool_name: str) -> str:
    """Full source of the tool function, including its ``@mcp.tool`` decorator."""
    return inspect.getsource(getattr(main_mod, tool_name))


class TestCreateApiTokenAllowedIpsAndRateLimit:
    def test_bare_call_body_unchanged(self, recording):
        result = _run(main_mod.npg_create_api_token(
            name="pipeline-bare", permissions=["*"]))
        assert result["success"] is True
        _m, path, body, _params = _single_post(recording)
        assert path == "/api/v1/api-tokens"
        assert body == {"name": "pipeline-bare", "permissions": ["*"]}

    def test_expires_in_still_sent_alone(self, recording):
        result = _run(main_mod.npg_create_api_token(
            name="t", permissions=["*"], expires_in="30d"))
        assert result["success"] is True
        _m, _path, body, _params = _single_post(recording)
        assert body == {"name": "t", "permissions": ["*"], "expires_in": "30d"}

    def test_allowed_ips_and_rate_limit_sent(self, recording):
        result = _run(main_mod.npg_create_api_token(
            name="scoped",
            permissions=["proxyhost:read"],
            allowed_ips=["127.0.0.1/32", "10.0.0.0/8"],
            rate_limit=50,
        ))
        assert result["success"] is True
        _m, _path, body, _params = _single_post(recording)
        assert body == {
            "name": "scoped",
            "permissions": ["proxyhost:read"],
            "allowed_ips": ["127.0.0.1/32", "10.0.0.0/8"],
            "rate_limit": 50,
        }

    def test_empty_allowlist_behaves_like_omitted(self, recording):
        result = _run(main_mod.npg_create_api_token(
            name="t", permissions=["*"], allowed_ips=[]))
        assert result["success"] is True
        _m, _path, body, _params = _single_post(recording)
        assert "allowed_ips" not in body

    def test_allowlist_is_copied_not_aliased(self, recording):
        supplied = ["192.0.2.1"]
        result = _run(main_mod.npg_create_api_token(
            name="t", permissions=["*"], allowed_ips=supplied))
        assert result["success"] is True
        _m, _path, body, _params = _single_post(recording)
        assert body["allowed_ips"] == supplied
        assert body["allowed_ips"] is not supplied

    @pytest.mark.parametrize("bad", [0, -1, True])
    def test_invalid_rate_limit_rejected_before_http(self, recording, bad):
        result = _run(main_mod.npg_create_api_token(
            name="t", permissions=["*"], rate_limit=bad))
        assert result["success"] is False
        assert "rate_limit" in result["error"]
        assert recording.calls == []

    def test_rate_limit_zero_message_is_actionable(self, recording):
        result = _run(main_mod.npg_create_api_token(
            name="t", permissions=["*"], rate_limit=0))
        assert result["success"] is False
        assert "positive integer" in result["error"]


class TestBanIpProxyHostScope:
    def test_global_ban_omits_scope_key(self, recording):
        result = _run(main_mod.npg_ban_ip(ip_address="203.0.113.9"))
        assert result["success"] is True
        _m, path, body, _params = _single_post(recording)
        assert path == "/api/v1/banned-ips"
        assert body == {
            "ip_address": "203.0.113.9",
            "reason": "Manual ban via API",
            "ban_time": 3600,
        }

    def test_blank_scope_behaves_like_global(self, recording):
        result = _run(main_mod.npg_ban_ip(
            ip_address="203.0.113.9", proxy_host_id="   "))
        assert result["success"] is True
        _m, _path, body, _params = _single_post(recording)
        assert "proxy_host_id" not in body

    def test_host_scoped_ban_sends_raw_uuid(self, recording):
        result = _run(main_mod.npg_ban_ip(
            ip_address="203.0.113.9",
            reason="abuse on one host",
            ban_time=0,
            proxy_host_id=HOST,
        ))
        assert result["success"] is True
        _m, _path, body, _params = _single_post(recording)
        assert body == {
            "ip_address": "203.0.113.9",
            "reason": "abuse on one host",
            "ban_time": 0,
            "proxy_host_id": HOST,
        }
        # A body id must never be URL-encoded.
        assert "%" not in body["proxy_host_id"]


class TestRevokeApiTokenReason:
    def test_no_reason_sends_no_body(self, recording):
        result = _run(main_mod.npg_revoke_api_token(token_id=TOKEN))
        assert result["success"] is True
        _m, path, body, _params = _single_post(recording)
        assert path == f"/api/v1/api-tokens/{TOKEN}/revoke"
        assert body is None

    def test_reason_sent_when_given(self, recording):
        result = _run(main_mod.npg_revoke_api_token(
            token_id=TOKEN, reason="pipeline param test"))
        assert result["success"] is True
        _m, _path, body, _params = _single_post(recording)
        assert body == {"reason": "pipeline param test"}


class TestDescriptionsMatchSignatures:
    """Signature change ⇒ description change, same commit (publish CI gate)."""

    def test_create_api_token_description_names_new_params(self):
        desc = _description("npg_create_api_token")
        assert "allowed_ips" in desc
        assert "rate_limit" in desc

    def test_ban_ip_description_names_proxy_host_id(self):
        desc = _description("npg_ban_ip")
        assert "proxy_host_id" in desc

    def test_revoke_api_token_description_names_reason(self):
        desc = _description("npg_revoke_api_token")
        assert "reason" in desc

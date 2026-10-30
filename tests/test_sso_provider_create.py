"""Regression tests for npg_create_sso_provider allowlist/group/role fields.

Bug class fixed here: the tool's ``description=`` advertised five parameters
(``allowed_email_domains``, ``allowed_emails``, ``group_claim``,
``required_group``, ``default_role_id``) that were absent from the function
signature and had no ``kwargs`` hatch, so an agent following the description
hit a Pydantic validation error and the fields were unreachable at create
time. Upstream ``SSOProviderRequest`` (swagger v2.65.3) accepts all five.

These tests run with no network access: ``_get_client`` is monkeypatched with
a recording fake so the tool's real code path (validation -> body build ->
HTTP call shape) executes end to end.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import npg_mcp.main as main_mod

NEW_FIELDS: dict[str, Any] = {
    "allowed_email_domains": ["example.com"],
    "allowed_emails": ["user@example.com"],
    "group_claim": "groups",
    "required_group": "npg-admins",
    "default_role_id": "11111111-1111-1111-1111-111111111111",
}


class _RecordingClient:
    """Fake NPGClient that records the last (method, path, body) call."""

    def __init__(self):
        self.calls = []

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        return {"id": "created-sso"}


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _base_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        slug="sso-test",
        name="SSO Test",
        issuer_url="https://idp.example.com",
        client_id="client-abc",
        client_secret="secret-xyz",
    )
    kwargs.update(overrides)
    return kwargs


class TestCreateSsoProviderBody:
    def test_allowlist_and_group_fields_reach_the_request_body(self, recording):
        result = _run(main_mod.npg_create_sso_provider(**_base_kwargs(**NEW_FIELDS)))

        assert result["success"] is True
        method, path, body = recording.calls[0]
        assert (method, path) == ("POST", "/api/v1/sso-providers")
        # Exact upstream field names from SSOProviderRequest.
        for field, value in NEW_FIELDS.items():
            assert body[field] == value, f"{field} not forwarded verbatim"
        assert body["slug"] == "sso-test"
        assert body["client_secret"] == "secret-xyz"

    def test_omitted_optional_fields_are_not_sent(self, recording):
        """A create must not invent allowlist/role values the caller never passed."""
        result = _run(main_mod.npg_create_sso_provider(**_base_kwargs()))

        assert result["success"] is True
        _, _, body = recording.calls[0]
        for field in NEW_FIELDS:
            assert field not in body, f"{field} sent despite being omitted"
        assert "scopes" not in body
        # trust_provider_email keeps its documented hardcoded default.
        assert body["trust_provider_email"] is False

    def test_explicit_empty_lists_are_forwarded(self, recording):
        """Empty allowlists are meaningful upstream (nobody signs in) — pass them through."""
        result = _run(
            main_mod.npg_create_sso_provider(
                **_base_kwargs(allowed_emails=[], allowed_email_domains=[])
            )
        )

        assert result["success"] is True
        _, _, body = recording.calls[0]
        assert body["allowed_emails"] == []
        assert body["allowed_email_domains"] == []

    def test_required_params_still_validated(self, recording):
        result = _run(main_mod.npg_create_sso_provider(**_base_kwargs(client_id="")))

        assert result["success"] is False
        assert recording.calls == [], "no API call should happen on validation failure"


class TestCreateSsoProviderSchemaParity:
    """The served schema must keep pace with the description (the original bug)."""

    def _tool(self):
        tools = {t.name: t for t in main_mod.mcp._tool_manager.list_tools()}
        return tools["npg_create_sso_provider"]

    def test_schema_exposes_every_advertised_field(self):
        props = self._tool().parameters["properties"]
        for field in NEW_FIELDS:
            assert field in props, f"{field} advertised in description but not in schema"

    def test_advertised_fields_are_optional(self):
        required = self._tool().parameters.get("required", [])
        assert set(required) == {"slug", "name", "issuer_url", "client_id"}, required
        for field in NEW_FIELDS:
            assert field not in required

    def test_description_does_not_name_unsupported_params(self):
        tool = self._tool()
        description = tool.description or ""
        props = set(tool.parameters["properties"])
        # Every upstream SSO field the description could reference must exist.
        candidates = set(NEW_FIELDS) | {
            "client_secret",
            "scopes",
            "trust_provider_email",
            "callback_base_url",
            "enabled",
            "allow_jit",
            "group_role_mappings",
        }
        ghosts = [n for n in candidates if n in description and n not in props]
        assert ghosts == [], f"description advertises params the schema rejects: {ghosts}"

    def test_description_within_desc_len_cap(self):
        assert len(self._tool().description) <= 460

"""Unit tests for npg_bulk_update_proxy_hosts (one field set, many hosts).

Verifies, without any network access (recording fake client):

* the exact per-host PUT body: MCP parameter names translated to API field
  names (``ssl_forced`` -> ``ssl_force_https``, ``ssl_cert_id`` ->
  ``certificate_id``) and instance ids coerced to plain strings,
* ``skip_nginx`` lands as a QUERY param (true by default, absent when false),
* ids dedupe on the URL-encoded form in first-seen order,
* per-host failure isolation: a dead host lands in ``hosts_failed`` while its
  siblings still update, and a batch reports ``success: true`` overall,
* unknown field keys / empty ``fields`` / an all-None body / empty or over-cap
  ``host_ids`` are rejected BEFORE any HTTP call (a mass mutation must never
  half-apply on a typo),
* the hoisted ``_PROXY_HOST_UPDATE_FIELD_MAP`` matches
  ``npg_update_proxy_host``'s signature (drift guard) and the single-host tool
  still builds the same body through it,
* annotations: idempotent PUT, not read-only, not destructive, no ``expand``.

Monkeypatches npg_mcp.main._get_client with a recording fake so the tools'
real code paths run end to end.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

import npg_mcp.main as main_mod
import npg_mcp.toolsets as toolsets
from npg_mcp.client import NPGError
from npg_mcp.main import (
    _BULK_HOST_LIMIT,
    _PROXY_HOST_UPDATE_FIELD_MAP,
    _PROXY_HOST_UPDATE_ID_FIELDS,
)


class _RecordingClient:
    """Fake NPGClient that records every mutating call."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail: set[str] = set()

    def put(self, path, body, params=None):
        self.calls.append(("PUT", path, body, params))
        if path in self.fail:
            raise NPGError("NPG API returned HTTP 404", "not found")
        return {"updated": True}

    def _bodies(self) -> list[dict]:
        return [call[2] for call in self.calls]

    def _params(self) -> list:
        return [call[3] for call in self.calls]


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _bulk(host_ids, fields, **kwargs):
    return _run(main_mod.npg_bulk_update_proxy_hosts(host_ids, fields, **kwargs))


class TestBodyTranslation:
    def test_two_field_set_hits_every_host_with_api_names(self, recording):
        result = _bulk(
            ["h1", "h2"],
            {"client_max_body_size": "25m", "ssl_forced": True},
        )

        assert result["success"] is True
        assert result["hosts_failed"] == []
        assert [entry["host_id"] for entry in result["data"]] == ["h1", "h2"]
        assert all(entry["success"] is True for entry in result["data"])
        assert recording._bodies() == [
            {"client_max_body_size": "25m", "ssl_force_https": True},
            {"client_max_body_size": "25m", "ssl_force_https": True},
        ]
        assert [call[1] for call in recording.calls] == [
            "/api/v1/proxy-hosts/h1",
            "/api/v1/proxy-hosts/h2",
        ]

    def test_id_fields_coerced_to_raw_strings(self, recording):
        _bulk(["h1"], {"ssl_cert_id": 12345, "access_list_id": 7})

        # Body values are NOT percent-encoded and ints become plain strings.
        assert recording._bodies() == [
            {"certificate_id": "12345", "access_list_id": "7"}
        ]

    def test_path_ids_are_url_encoded_once(self, recording):
        _bulk(["a/b"], {"client_max_body_size": "1m"})

        assert recording.calls[0][1] == "/api/v1/proxy-hosts/a%2Fb"

    def test_skip_nginx_true_is_a_query_param(self, recording):
        _bulk(["h1"], {"client_max_body_size": "1m"})

        assert recording._params() == [{"skip_nginx": "true"}]

    def test_skip_nginx_false_sends_no_query_param(self, recording):
        _bulk(["h1"], {"client_max_body_size": "1m"}, skip_nginx=False)

        assert recording._params() == [None]


class TestDedupeAndIsolation:
    def test_duplicate_ids_updated_once_first_seen_order(self, recording):
        result = _bulk([1, "1", 2], {"client_max_body_size": "1m"})

        assert [entry["host_id"] for entry in result["data"]] == ["1", "2"]
        assert [call[1] for call in recording.calls] == [
            "/api/v1/proxy-hosts/1",
            "/api/v1/proxy-hosts/2",
        ]

    def test_one_failing_host_never_aborts_the_batch(self, recording):
        recording.fail.add("/api/v1/proxy-hosts/bad")
        result = _bulk(["good", "bad"], {"client_max_body_size": "1m"})

        assert result["success"] is True
        assert result["hosts_failed"] == ["bad"]
        good, bad = result["data"]
        assert good["success"] is True and good["result"] == {"updated": True}
        assert bad["success"] is False
        assert "404" in bad["error"]
        assert bad["hint"]

    def test_blank_id_fails_only_that_entry(self, recording):
        result = _bulk(["h1", ""], {"client_max_body_size": "1m"})

        assert result["hosts_failed"] == [""]
        # The valid host was still updated; the blank id never reached HTTP.
        assert [call[1] for call in recording.calls] == ["/api/v1/proxy-hosts/h1"]


class TestRejectionsBeforeAnyHttp:
    def test_unknown_field_key_rejected_with_allowed_list(self, recording):
        result = _bulk(["h1"], {"client_max_body_sze": "25m"})

        assert result["success"] is False
        assert "client_max_body_sze" in result["error"]
        assert "npg_update_proxy_host" in result["error"]
        assert "client_max_body_size" in result["error"]  # the allowed list
        assert recording.calls == []

    def test_empty_fields_rejected(self, recording):
        result = _bulk(["h1"], {})

        assert result["success"] is False
        assert "fields" in result["error"]
        assert recording.calls == []

    def test_all_none_fields_rejected_as_no_op(self, recording):
        result = _bulk(["h1"], {"client_max_body_size": None})

        assert result["success"] is False
        assert "empty update body" in result["error"]
        assert recording.calls == []

    def test_empty_host_ids_rejected(self, recording):
        result = _bulk([], {"client_max_body_size": "1m"})

        assert result["success"] is False
        assert "host_ids" in result["error"]
        assert recording.calls == []

    def test_over_cap_rejected(self, recording):
        ids = [f"h{n}" for n in range(_BULK_HOST_LIMIT + 1)]
        result = _bulk(ids, {"client_max_body_size": "1m"})

        assert result["success"] is False
        assert str(_BULK_HOST_LIMIT) in result["error"]
        assert recording.calls == []


class TestFieldMapParity:
    def test_field_map_matches_update_signature(self):
        """The map must exactly mirror npg_update_proxy_host's params.

        ``host_id`` is the path id, ``skip_nginx`` and ``ddns_remove_provider``
        are PUT QUERY params (never body fields), so all three are excluded.
        """
        sig = inspect.signature(main_mod.npg_update_proxy_host)
        params = set(sig.parameters)
        assert set(_PROXY_HOST_UPDATE_FIELD_MAP) == params - {
            "host_id",
            "skip_nginx",
            "ddns_remove_provider",
        }

    def test_id_fields_are_a_subset_of_the_map(self):
        assert _PROXY_HOST_UPDATE_ID_FIELDS <= set(_PROXY_HOST_UPDATE_FIELD_MAP)

    def test_single_host_tool_builds_the_same_body(self, recording):
        """Regression for the map hoist: one-host output is unchanged."""
        _run(
            main_mod.npg_update_proxy_host(
                host_id="h1",
                client_max_body_size="25m",
                ssl_forced=False,
                ssl_cert_id=42,
                tags=["a"],
            )
        )

        assert recording.calls[0][1] == "/api/v1/proxy-hosts/h1"
        assert recording._bodies() == [
            {
                "client_max_body_size": "25m",
                "ssl_force_https": False,
                "certificate_id": "42",
                "tags": ["a"],
            }
        ]
        # Single-host default keeps per-host nginx regen.
        assert recording._params() == [None]


class TestClassification:
    def test_annotations_are_idempotent_non_destructive(self):
        hints = toolsets.annotations_for("npg_bulk_update_proxy_hosts")
        assert hints is not None
        assert hints.readOnlyHint is False
        assert hints.destructiveHint is False
        assert hints.idempotentHint is True
        assert hints.openWorldHint is True

    def test_standard_tier_exposes_it(self):
        names = toolsets._discover_tool_names()
        assert "npg_bulk_update_proxy_hosts" in toolsets.tier_allowed(names, "standard")
        assert "npg_bulk_update_proxy_hosts" not in toolsets.tier_allowed(names, "read")

    def test_mutating_tool_declares_no_expand(self):
        sig = inspect.signature(main_mod.npg_bulk_update_proxy_hosts)
        assert "expand" not in sig.parameters

"""Unit tests for npg_bulk_export_proxy_hosts (bounded multi-host export).

Verifies, without any network access (recording fake client):

* one bundle per host, with the same shape npg_import_proxy_host consumes,
* the single-host npg_export_proxy_host output is unchanged after the bundle
  builder was extracted into the shared _build_export_bundle helper,
* instance-scoped metadata is stripped and cross-instance UUID refs move to
  ``external_refs`` (never copied into a section),
* section subsetting issues only the requested section GETs,
* ids dedupe on the URL-encoded form in first-seen order,
* per-host failure isolation: a dead host lands in ``hosts_failed`` while its
  siblings still export; a failing sub-section keeps the host exported,
* empty and over-cap batches are rejected before any HTTP call,
* the tool is classified read-only from its helper's routes (the annotation
  harvester follows private module-level helpers).

Monkeypatches npg_mcp.main._get_client with a recording fake so the tools'
real code paths run end to end.
"""

from __future__ import annotations

import asyncio
import copy

import pytest

import npg_mcp.main as main_mod
from npg_mcp.client import NPGError
from npg_mcp.main import _BULK_EXPORT_HOST_LIMIT

# Canned section payloads, shaped like the NPG API's per-host responses.
_SECTIONS: dict[str, dict] = {
    "host": {
        "id": "row-uuid",
        "proxy_host_id": "",
        "domain_names": ["app.example.com"],
        "forward_scheme": "http",
        "forward_host": "10.0.0.10",
        "forward_port": 8080,
        "certificate_id": "cert-uuid",
        "access_list_id": "",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "custom_locations": "",
        "enabled": True,
    },
    "rate_limit": {
        "id": "rl-row",
        "proxy_host_id": "p",
        "enabled": True,
        "requests_per_second": 5,
    },
    "bot_filter": {"id": "bf-row", "proxy_host_id": "p", "enabled": False},
    "security_headers": {"id": "sh-row", "proxy_host_id": "p", "enabled": True},
    "upstream": {"id": "up-row", "proxy_host_id": "p", "servers": []},
    "geo": {"id": "geo-row", "proxy_host_id": "p", "enabled": False},
    "challenge": {"id": "ch-row", "proxy_host_id": "p", "enabled": False},
    "fail2ban": {"id": "f2b-row", "proxy_host_id": "p", "enabled": True},
    "cloud_blocking": {"id": "cb-row", "proxy_host_id": "p", "blocked_providers": []},
    "waf": {"id": "waf-row", "proxy_host_id": "p", "enabled": False},
    "uri_block": {"id": "ub-row", "proxy_host_id": "p", "enabled": False},
}

# Longest suffixes first: the host route ("/api/v1/proxy-hosts/{id}") has no
# suffix, so every other route must be matched before the host fallback.
_PATH_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("/blocked-cloud-providers", "cloud_blocking"),
    ("/security-headers", "security_headers"),
    ("/rate-limit", "rate_limit"),
    ("/bot-filter", "bot_filter"),
    ("/fail2ban", "fail2ban"),
    ("/challenge", "challenge"),
    ("/upstream", "upstream"),
    ("/uri-block", "uri_block"),
    ("/geo", "geo"),
)


def _section_for(path: str) -> str:
    if path.startswith("/api/v1/waf/hosts/"):
        return "waf"
    for suffix, section in _PATH_SUFFIXES:
        if path.endswith(suffix):
            return section
    return "host"


class _RecordingClient:
    """Fake NPGClient that records every call and serves canned sections."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail: set[str] = set()

    def get(self, path, params=None):
        self.calls.append(("GET", path, None, params))
        if path in self.fail:
            raise NPGError("NPG API returned HTTP 404", "not found")
        return copy.deepcopy(_SECTIONS[_section_for(path)])

    def _paths(self) -> list[str]:
        return [call[1] for call in self.calls]


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


class TestBulkExportBundles:
    def test_one_bundle_per_host_with_all_sections(self, recording):
        result = _run(main_mod.npg_bulk_export_proxy_hosts(["h1", "h2"]))

        assert result["success"] is True
        assert set(result["data"]) == {"h1", "h2"}
        assert result["hosts_failed"] == []
        for host_id in ("h1", "h2"):
            entry = result["data"][host_id]
            assert entry["success"] is True
            assert entry["sections_failed"] == []
            bundle = entry["bundle"]
            assert bundle["schema_version"] == 1
            assert bundle["source_host_id"] == host_id
            assert set(bundle["sections"]) == set(_SECTIONS)
        # 11 section GETs per host, nothing more.
        assert len(recording.calls) == 22
        assert all(path.startswith("/api/v1/") for path in recording._paths())

    def test_metadata_stripped_and_external_refs_moved(self, recording):
        result = _run(main_mod.npg_bulk_export_proxy_hosts(["h1"]))
        bundle = result["data"]["h1"]["bundle"]
        host_section = bundle["sections"]["host"]

        for stripped in ("id", "proxy_host_id", "created_at", "updated_at"):
            assert stripped not in host_section
        assert "certificate_id" not in host_section
        # Empty instance refs are dropped, never exported as "".
        assert "access_list_id" not in host_section
        assert bundle["external_refs"] == {"certificate_id": "cert-uuid"}
        assert bundle["sections"]["rate_limit"] == {
            "enabled": True,
            "requests_per_second": 5,
        }
        # Warning order is preserved from the source implementation.
        assert bundle["warnings"] == [
            "instance-scoped ref certificate_id moved to external_refs — import "
            "flags it, never copies it blind; re-resolve on the target instance"
        ]

    def test_section_subsetting_issues_only_requested_get(self, recording):
        result = _run(
            main_mod.npg_bulk_export_proxy_hosts(["h1"], sections=["host", "geo"])
        )
        bundle = result["data"]["h1"]["bundle"]
        assert set(bundle["sections"]) == {"host", "geo"}
        assert len(recording.calls) == 2
        assert sorted(recording._paths()) == [
            "/api/v1/proxy-hosts/h1",
            "/api/v1/proxy-hosts/h1/geo",
        ]

    def test_duplicate_ids_fetched_once_first_seen_order(self, recording):
        result = _run(main_mod.npg_bulk_export_proxy_hosts([1, "1", 1]))
        # int 1 and str "1" share the same URL form, so one host is exported.
        assert list(result["data"]) == ["1"]
        assert len(recording.calls) == 11

    def test_ids_are_url_encoded_in_section_paths(self, recording):
        _run(main_mod.npg_bulk_export_proxy_hosts(["a/b"]))
        assert all("/api/v1/" in path for path in recording._paths())
        assert all("a%2Fb" in path for path in recording._paths())


class TestFailureIsolation:
    def test_dead_host_lands_in_hosts_failed_siblings_export(self, recording):
        recording.fail.add("/api/v1/proxy-hosts/bad")
        result = _run(main_mod.npg_bulk_export_proxy_hosts(["good", "bad"]))

        assert result["success"] is True
        assert result["hosts_failed"] == ["bad"]
        assert result["data"]["good"]["success"] is True
        bad = result["data"]["bad"]
        assert bad["success"] is False
        assert "404" in bad["error"]
        assert bad["hint"]
        # The bundle is still returned for inspection, minus the host core.
        assert "host" not in bad["bundle"]["sections"]
        assert "host" in bad["sections_failed"]

    def test_subsection_failure_keeps_host_exported(self, recording):
        recording.fail.add("/api/v1/proxy-hosts/h1/geo")
        result = _run(main_mod.npg_bulk_export_proxy_hosts(["h1"]))

        assert result["hosts_failed"] == []
        entry = result["data"]["h1"]
        assert entry["success"] is True
        assert entry["sections_failed"] == ["geo"]
        assert "geo" not in entry["bundle"]["sections"]
        assert any("section geo not exported" in w for w in entry["bundle"]["warnings"])


class TestValidation:
    def test_empty_host_ids_rejected_before_any_call(self, recording):
        result = _run(main_mod.npg_bulk_export_proxy_hosts([]))
        assert result["success"] is False
        assert "host_ids" in result["error"]
        assert recording.calls == []

    def test_over_cap_rejected_before_any_call(self, recording):
        ids = [f"host-{i:03d}" for i in range(_BULK_EXPORT_HOST_LIMIT + 1)]
        result = _run(main_mod.npg_bulk_export_proxy_hosts(ids))
        assert result["success"] is False
        assert f"limit of {_BULK_EXPORT_HOST_LIMIT}" in result["error"]
        assert recording.calls == []

    def test_cap_is_lower_than_the_bulk_read_cap(self):
        assert _BULK_EXPORT_HOST_LIMIT == 20
        assert _BULK_EXPORT_HOST_LIMIT < main_mod._BULK_HOST_LIMIT

    def test_unknown_section_rejected_before_any_call(self, recording):
        result = _run(
            main_mod.npg_bulk_export_proxy_hosts(["h1"], sections=["nope"])
        )
        assert result["success"] is False
        assert "Invalid section name" in result["error"]
        assert recording.calls == []


class TestSingleHostExportUnchanged:
    def test_envelope_and_bundle_shape_match_pre_refactor(self, recording):
        result = _run(main_mod.npg_export_proxy_host("h1"))

        assert set(result) == {"success", "data", "sections_failed"}
        assert result["success"] is True
        assert result["sections_failed"] == []
        assert set(result["data"]) == {
            "schema_version",
            "exported_at",
            "source_host_id",
            "sections",
            "external_refs",
            "warnings",
        }
        assert result["data"]["source_host_id"] == "h1"

    def test_single_host_bundle_equals_bulk_bundle(self, recording):
        single = _run(main_mod.npg_export_proxy_host("h1"))
        bulk = _run(main_mod.npg_bulk_export_proxy_hosts(["h1"]))

        single_bundle = dict(single["data"])
        bulk_bundle = dict(bulk["data"]["h1"]["bundle"])
        # exported_at is a timestamp; everything else must be identical.
        single_bundle.pop("exported_at")
        bulk_bundle.pop("exported_at")
        assert single_bundle == bulk_bundle


class TestDerivedClassification:
    def test_routes_are_harvested_through_the_shared_helper(self):
        from npg_mcp.toolsets import _tool_verbs

        verbs = _tool_verbs()
        # Both tools delegate their GETs to _build_export_bundle; the harvester
        # follows private module-level helpers.
        assert verbs["npg_bulk_export_proxy_hosts"] == frozenset({"get"})
        assert verbs["npg_export_proxy_host"] == frozenset({"get"})

    def test_tool_is_read_only_and_in_the_higher_tiers(self):
        from npg_mcp.toolsets import _discover_tool_names, annotations_for, tier_allowed

        annotations = annotations_for("npg_bulk_export_proxy_hosts")
        assert annotations is not None
        assert annotations.readOnlyHint is True

        names = _discover_tool_names()
        assert "npg_bulk_export_proxy_hosts" not in tier_allowed(names, "read")
        assert "npg_bulk_export_proxy_hosts" in tier_allowed(names, "standard")
        assert "npg_bulk_export_proxy_hosts" in tier_allowed(names, "full")

"""Unit tests for the compact/full modes of ``npg_list_cloud_providers``.

The default ``compact=True`` must keep the response small: identity plus
configured state per provider, with ``ip_ranges`` replaced by a count and the
synopsis clipped. ``compact=False`` must stay byte-for-byte identical to the
pre-change payload (every field the API returns, full ``ip_ranges``, full
``description``) so existing callers are unaffected.

No network access: ``_get_client`` is monkeypatched with a recording fake, so
the tool's real code paths run (validation -> GET -> compact -> slice).
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod
from npg_mcp.main import (
    _COMPACT_DESCRIPTION_MAX,
    _compact_cloud_provider,
    _compact_cloud_provider_list,
)

PROVIDER_PATH = "/api/v1/cloud-providers"

FULL = [
    {
        "id": "ee7d21eb-526f-4e8c-af6e-e7f151c3a10f",
        "name": "Inspect Alpha",
        "slug": "inspect-alpha",
        "region": "us",
        "description": "Alpha provider " + "x" * 400,
        "ip_ranges": ["10.1.0.0/16", "10.2.0.0/16", "10.3.0.0/16"],
        "enabled": True,
        "created_at": "2026-11-02T15:55:00.822356+09:00",
        "updated_at": "2026-11-02T15:55:00.822356+09:00",
    },
    {
        "id": "d39d388b-8734-4817-b310-a9b53058f925",
        "name": "Inspect Beta",
        "slug": "inspect-beta",
        "region": "eu",
        "description": "Short synopsis.",
        "ip_ranges": ["172.16.0.0/24"],
        "enabled": False,
        "created_at": "2026-11-02T15:55:00.830279+09:00",
        "updated_at": "2026-11-02T15:55:00.830279+09:00",
    },
]


class _FakeClient:
    """Recording fake returning a fixed payload for the cloud-provider list."""

    def __init__(self, data):
        self.data = data
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        assert path == PROVIDER_PATH
        return self.data


def _fake(monkeypatch, data):
    client = _FakeClient(data)
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


class TestCompactCloudProviderRow:
    def test_keeps_identity_state_and_range_count(self):
        row = _compact_cloud_provider(FULL[0])
        assert row["id"] == FULL[0]["id"]
        assert row["slug"] == "inspect-alpha"
        assert row["name"] == "Inspect Alpha"
        assert row["region"] == "us"
        assert row["enabled"] is True
        assert row["ip_range_count"] == 3
        assert "ip_ranges" not in row
        assert "created_at" not in row
        assert "updated_at" not in row

    def test_long_description_clipped_to_cap_with_ellipsis(self):
        row = _compact_cloud_provider(FULL[0])
        assert len(row["description"]) == _COMPACT_DESCRIPTION_MAX
        assert row["description"].endswith("…")
        assert row["description"].startswith("Alpha provider ")

    def test_short_description_untouched(self):
        row = _compact_cloud_provider(FULL[1])
        assert row["description"] == "Short synopsis."

    def test_disabled_state_preserved(self):
        assert _compact_cloud_provider(FULL[1])["enabled"] is False

    def test_description_at_exact_cap_not_clipped(self):
        item = {"slug": "s", "description": "y" * _COMPACT_DESCRIPTION_MAX}
        row = _compact_cloud_provider(item)
        assert row["description"] == "y" * _COMPACT_DESCRIPTION_MAX

    def test_blank_or_missing_description_omitted(self):
        blank = {"slug": "s", "description": "  "}
        assert "description" not in _compact_cloud_provider(blank)
        assert "description" not in _compact_cloud_provider({"slug": "s"})

    def test_absent_ip_ranges_omits_count(self):
        assert "ip_range_count" not in _compact_cloud_provider({"slug": "s"})

    def test_non_dict_entry_passed_through(self):
        assert _compact_cloud_provider("odd") == "odd"
        assert _compact_cloud_provider(None) is None

    def test_unknown_upstream_fields_dropped_not_renamed(self):
        row = _compact_cloud_provider({"slug": "s", "display_name": "X", "id": "1"})
        assert row == {"slug": "s", "id": "1"}


class TestCompactListShapes:
    def test_bare_list_compacted(self):
        rows = _compact_cloud_provider_list(FULL)
        assert [r["slug"] for r in rows] == ["inspect-alpha", "inspect-beta"]
        assert all("ip_ranges" not in r for r in rows)

    def test_wrapped_list_compacted_in_place(self):
        data = {"providers": list(FULL), "total": 2}
        out = _compact_cloud_provider_list(data)
        assert isinstance(out, dict)
        assert out["total"] == 2
        rows = out["providers"]
        assert isinstance(rows, list)
        assert [r["slug"] for r in rows] == ["inspect-alpha", "inspect-beta"]
        assert "ip_ranges" in data["providers"][0]  # source not mutated

    def test_unexpected_shape_unchanged(self):
        assert _compact_cloud_provider_list({"status": "ok"}) == {"status": "ok"}
        assert _compact_cloud_provider_list(None) is None


class TestListCloudProvidersTool:
    def test_default_is_compact(self, monkeypatch):
        data = [dict(item) for item in FULL]
        client = _fake(monkeypatch, data)
        result = _run(main_mod.npg_list_cloud_providers())

        assert result["success"] is True
        assert "paging" not in result
        rows = result["data"]
        assert [r["slug"] for r in rows] == ["inspect-alpha", "inspect-beta"]
        assert all("ip_ranges" not in r for r in rows)
        assert all(len(r["description"]) <= _COMPACT_DESCRIPTION_MAX for r in rows)
        assert client.calls == [("GET", PROVIDER_PATH, None)]

    def test_compact_false_is_byte_identical_to_upstream(self, monkeypatch):
        data = [dict(item) for item in FULL]
        client = _fake(monkeypatch, data)
        result = _run(main_mod.npg_list_cloud_providers(compact=False))

        assert result == {"success": True, "data": data}
        assert result["data"][0]["ip_ranges"] == FULL[0]["ip_ranges"]
        assert result["data"][0]["description"] == FULL[0]["description"]
        assert client.calls == [("GET", PROVIDER_PATH, None)]

    def test_compact_true_explicit_matches_default(self, monkeypatch):
        _fake(monkeypatch, [dict(item) for item in FULL])
        default = _run(main_mod.npg_list_cloud_providers())
        explicit = _run(main_mod.npg_list_cloud_providers(compact=True))
        assert default == explicit

    def test_compact_with_paging_slices_compacted_rows(self, monkeypatch):
        _fake(monkeypatch, [dict(item) for item in FULL])
        result = _run(main_mod.npg_list_cloud_providers(limit=1, offset=1))

        assert [r["slug"] for r in result["data"]] == ["inspect-beta"]
        assert "ip_ranges" not in result["data"][0]
        assert result["paging"]["total"] == 2
        assert result["paging"]["returned"] == 1
        assert result["paging"]["offset"] == 1
        assert "mcp-side" in result["paging"]["applied"]

    def test_compact_false_with_paging_slices_full_rows(self, monkeypatch):
        _fake(monkeypatch, [dict(item) for item in FULL])
        result = _run(
            main_mod.npg_list_cloud_providers(limit=1, offset=0, compact=False)
        )

        assert result["data"][0]["ip_ranges"] == FULL[0]["ip_ranges"]
        assert result["paging"]["total"] == 2
        assert result["paging"]["returned"] == 1

    def test_empty_upstream_list(self, monkeypatch):
        _fake(monkeypatch, [])
        result = _run(main_mod.npg_list_cloud_providers())
        assert result == {"success": True, "data": []}

    def test_null_upstream_body_passes_through(self, monkeypatch):
        # GET /cloud-providers answers `null` on a pristine instance.
        _fake(monkeypatch, None)
        result = _run(main_mod.npg_list_cloud_providers())
        assert result == {"success": True, "data": None}

    def test_negative_offset_still_rejected_before_http(self, monkeypatch):
        client = _fake(monkeypatch, [])
        result = _run(main_mod.npg_list_cloud_providers(offset=-1))
        assert result["success"] is False
        assert "offset" in result["error"]
        assert client.calls == []

    def test_upstream_error_becomes_error_envelope(self, monkeypatch):
        class _Boom:
            def get(self, path, params=None):
                raise RuntimeError("NPG API returned HTTP 500")

        monkeypatch.setattr(main_mod, "_get_client", lambda: _Boom())
        result = _run(main_mod.npg_list_cloud_providers())
        assert result["success"] is False
        assert "HTTP 500" in result["error"]


class TestToolSignatureContract:
    def test_compact_param_defaults_true(self):
        import inspect

        sig = inspect.signature(main_mod.npg_list_cloud_providers)
        assert sig.parameters["compact"].default is True
        assert sig.parameters["compact"].annotation in (bool, "bool")

    def test_description_documents_both_modes(self):
        from npg_mcp import main as m

        tools = {t.name: t for t in asyncio.run(m.mcp.list_tools())}
        desc = tools["npg_list_cloud_providers"].description
        assert "compact=true" in desc
        assert "compact=false" in desc
        assert "npg_get_cloud_provider" in desc
        assert len(desc) <= 460


@pytest.mark.parametrize("item", FULL)
def test_compact_row_is_smaller_than_full_row(item):
    import json

    compact = _compact_cloud_provider(item)
    assert len(json.dumps(compact)) < len(json.dumps(item))

"""Unit tests for the shared MCP-side result cap (npg_mcp.resultcap).

Covers the whole feature without any network access:

* ``NPG_MAX_RESULT_CHARS`` parsing (default / invalid / floor / ceiling).
* Under-budget results are returned untouched (same object, byte-identical).
* Boundary truncation cases demanded by the feature contract:
  - a short list that fits (untouched),
  - one item larger than the whole budget (trailing item dropped, prefix intact),
  - one string value larger than the whole budget (clamped, marker in place),
  - many small array items (trailing items dropped, JSON still complete),
  - a payload with no array and no long string (JSON-text fallback).
* Envelope contract: ``success``/``data`` survive, a ``truncated`` object carries
  total_chars / returned_chars / omitted_items / clamped_strings / hint, and the
  returned result is always complete, parseable JSON that lands under the cap.
* The retry hint names only parameters the tool actually declares.
* ``expand=true`` lifts the cap end to end through the real FastMCP tool surface.
* Instrumentation guards: only tools that declare ``expand`` are capped,
  ``npg_download_log_file`` keeps its own 256 KB cap, instrumenting twice is a
  no-op, and every read-only tool declares ``expand`` (drift guard).

Pure in-process tests — a recording fake client replaces the NPG API.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import npg_mcp.main as main_mod
import npg_mcp.resultcap as resultcap
import npg_mcp.toolsets as toolsets


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _size(value) -> int:
    return len(_dumps(value))


LIMIT = 4096


# ── NPG_MAX_RESULT_CHARS parsing ───────────────────────────────────────
class TestMaxResultCharsParsing:
    def test_default_when_unset(self):
        assert resultcap._parse_max_result_chars("") == 65536
        assert resultcap.DEFAULT_MAX_RESULT_CHARS == 65536

    def test_explicit_value(self):
        assert resultcap._parse_max_result_chars("20000") == 20000

    def test_invalid_falls_back_to_default(self):
        assert resultcap._parse_max_result_chars("65kb") == 65536
        assert resultcap._parse_max_result_chars("  ") == 65536

    def test_below_floor_clamps(self):
        floor = resultcap._MIN_MAX_RESULT_CHARS
        assert resultcap._parse_max_result_chars("10") == floor

    def test_above_ceiling_clamps(self):
        assert (
            resultcap._parse_max_result_chars("999999999")
            == resultcap._MAX_MAX_RESULT_CHARS
        )

    def test_env_var_name_is_documented(self):
        assert resultcap.ENV_VAR == "NPG_MAX_RESULT_CHARS"
        assert resultcap.max_result_chars() >= resultcap._MIN_MAX_RESULT_CHARS


# ── Under-budget passthrough ───────────────────────────────────────────
class TestPassthrough:
    def test_short_list_is_returned_untouched(self):
        payload = {"success": True, "data": [{"id": 1}, {"id": 2}]}
        out = resultcap.cap_result(payload, limit=LIMIT)
        # Same object: no reshaping, no added keys.
        assert out is payload
        assert "truncated" not in out
        assert _dumps(out) == _dumps(payload)

    def test_realistic_small_envelope_untouched(self):
        payload = {
            "success": True,
            "data": {"id": "abc", "domain_names": ["a.example.com"]},
            "message": "ok",
        }
        assert resultcap.cap_result(payload, limit=65536) is payload

    def test_non_dict_result_under_budget(self):
        payload = [1, 2, 3]
        assert resultcap.cap_result(payload, limit=LIMIT) is payload


# ── Boundary truncation ────────────────────────────────────────────────
class TestTruncationBoundaries:
    @staticmethod
    def _assert_common(out, limit, original):
        # Complete, parseable JSON that fits the ceiling.
        assert json.loads(_dumps(out)) is not None
        assert _size(out) <= limit
        meta = out["truncated"]
        assert meta["total_chars"] == _size(original)
        assert meta["returned_chars"] == _size(out)
        assert meta["returned_chars"] < meta["total_chars"]
        assert isinstance(meta["hint"], str) and meta["hint"]
        assert "NPG_MAX_RESULT_CHARS" in meta["hint"]
        assert out["success"] is True

    def test_many_small_items_drops_trailing_items(self):
        data = [{"i": i, "name": f"item-{i:04d}"} for i in range(600)]
        original = {"success": True, "data": data}
        out = resultcap.cap_result(original, tool_name="npg_list_x", limit=LIMIT)

        self._assert_common(out, LIMIT, original)
        kept = out["data"]
        assert isinstance(kept, list)
        assert 0 < len(kept) < len(data)
        # Trailing items dropped only: the retained prefix is byte-identical.
        assert kept == data[: len(kept)]
        assert out["truncated"]["omitted_items"] == len(data) - len(kept)

    def test_one_item_larger_than_budget(self):
        huge_item = {f"k{i}": i for i in range(4000)}
        original = {"success": True, "data": [huge_item]}
        out = resultcap.cap_result(original, tool_name="npg_list_x", limit=LIMIT)

        self._assert_common(out, LIMIT, original)
        assert out["data"] == []
        assert out["truncated"]["omitted_items"] == 1

    def test_oversized_head_item_drops_the_tail_it_cannot_help(self):
        """A list whose FIRST item alone busts the budget loses the array.

        Trailing-item dropping cannot fit an oversized leading item, so the
        array is emptied rather than returning a partial item or a gutted one
        (a row with silently-empty nested arrays would be misleading data).
        The metadata reports the omission and the hint points at the tool's
        own paging parameters, which is the documented way out.
        """
        huge_item = {f"k{i}": i for i in range(4000)}
        original = {
            "success": True,
            "data": [huge_item, {"id": "small-1"}, {"id": "small-2"}],
        }
        out = resultcap.cap_result(
            original,
            tool_name="npg_list_proxy_hosts",
            params=frozenset({"limit", "offset"}),
            limit=LIMIT,
        )

        self._assert_common(out, LIMIT, original)
        assert out["data"] == []
        assert out["truncated"]["omitted_items"] == 3
        assert "limit" in out["truncated"]["hint"]
        assert "offset" in out["truncated"]["hint"]

    def test_one_huge_string_value_is_clamped(self):
        blob = "A" * 200_000
        original = {"success": True, "data": {"id": "x", "content": blob}}
        out = resultcap.cap_result(original, tool_name="npg_download_x", limit=LIMIT)

        self._assert_common(out, LIMIT, original)
        clamped = out["data"]["content"]
        assert clamped.startswith("A" * 64)
        assert "[clamped " in clamped
        assert len(clamped) < len(blob)
        # Nothing else in the payload was touched.
        assert out["data"]["id"] == "x"
        assert out["truncated"]["clamped_strings"] == 1
        assert out["truncated"]["omitted_items"] == 0

    def test_no_array_no_long_string_falls_back_to_json_text(self):
        wide = {f"k{i}": i for i in range(4000)}
        original = {"success": True, "data": wide}
        out = resultcap.cap_result(original, tool_name="npg_get_settings", limit=LIMIT)

        assert _size(out) <= LIMIT
        assert out["success"] is True
        # The fallback keeps the payload as one clamped string — complete JSON,
        # never a half-written structure.
        assert isinstance(out["data"], str)
        assert "[clamped " in out["data"]
        assert out["truncated"]["total_chars"] == _size(original)

    def test_nested_arrays_are_trimmed_not_broken(self):
        data = [
            {"id": i, "items": [{"n": f"v{j}"} for j in range(20)]}
            for i in range(300)
        ]
        original = {"success": True, "data": data}
        out = resultcap.cap_result(original, tool_name="npg_bulk_get_x", limit=LIMIT)

        self._assert_common(out, LIMIT, original)
        assert isinstance(out["data"], list)
        for row in out["data"]:
            # Every surviving row keeps its own structure intact.
            assert set(row) == {"id", "items"}
            assert isinstance(row["items"], list)

    def test_error_envelope_passes_through(self):
        payload = {"success": False, "error": "boom", "hint": "retry"}
        assert resultcap.cap_result(payload, limit=LIMIT) is payload


# ── Retry hints ────────────────────────────────────────────────────────
class TestRetryHint:
    def _hint(self, tool_name, params, limit=LIMIT):
        return resultcap._retry_hint(tool_name, frozenset(params), limit)

    def test_names_limit_and_offset_when_present(self):
        hint = self._hint("npg_list_proxy_hosts", {"page", "limit", "offset"})
        assert "limit" in hint
        assert "offset" in hint
        assert "expand=true" in hint

    def test_names_sections_when_present(self):
        hint = self._hint("npg_bulk_get_proxy_host_full", {"host_ids", "sections"})
        assert "sections" in hint
        assert "limit" not in hint.replace("65536", "")

    def test_names_lines_when_present(self):
        hint = self._hint("npg_view_log_file", {"filename", "lines", "location"})
        assert "lines" in hint

    def test_no_paging_params_says_so_and_offers_expand(self):
        hint = self._hint("npg_get_settings", set())
        assert "no paging parameters" in hint
        assert "expand=true" in hint

    def test_payload_tools_warn_the_payload_is_undecodable(self):
        hint = self._hint("npg_download_backup", {"backup_id"})
        assert "cannot be decoded" in hint
        assert "expand=true" in hint

    def test_hint_mentions_the_cap_value(self):
        assert "4096" in self._hint("npg_get_settings", set())


# ── Tool instrumentation ───────────────────────────────────────────────
class _HugeListClient:
    """Fake NPGClient returning a payload well over the test budget."""

    def __init__(self, rows: int = 800):
        self.rows = rows

    def get(self, path, params=None):
        return {
            "data": [{"id": f"row-{i}", "name": f"name-{i}"} for i in range(self.rows)],
            "total": self.rows,
        }


@pytest.fixture
def small_cap(monkeypatch):
    monkeypatch.setattr(resultcap, "_MAX_RESULT_CHARS", LIMIT)
    return LIMIT


def _tool(name: str):
    """Return the served (``tools/list``) Tool object for *name*."""
    resultcap.instrument_tools(main_mod.mcp)
    for tool in asyncio.run(main_mod.mcp.list_tools()):
        if tool.name == name:
            return tool
    raise AssertionError(f"tool {name} not registered")


def _schema_properties(name: str) -> dict:
    return _tool(name).inputSchema.get("properties", {})


def _call(name: str, arguments: dict):
    """Call a tool through the real FastMCP tool manager (validation included)."""
    resultcap.instrument_tools(main_mod.mcp)
    return asyncio.run(main_mod.mcp._tool_manager.call_tool(name, arguments))


class TestInstrumentation:
    def test_tool_count_and_read_tier_unchanged(self):
        names = toolsets._discover_tool_names()
        assert len(names) == 320
        assert len(toolsets.tier_allowed(names, "read")) == 145
        assert len(toolsets.tier_allowed(names, "standard")) == 273
        assert len(toolsets.tier_allowed(names, "full")) == 320

    def test_cap_applies_end_to_end_and_expand_lifts_it(self, monkeypatch, small_cap):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _HugeListClient())

        capped = _call("npg_list_countries", {})
        assert capped["success"] is True
        assert "truncated" in capped
        assert _size(capped) <= LIMIT
        assert capped["truncated"]["omitted_items"] > 0

        full = _call("npg_list_countries", {"expand": True})
        assert "truncated" not in full
        # expand=true returns the complete, untouched payload.
        assert len(full["data"]["data"]) == 800

    def test_expand_is_advertised_in_the_served_schema(self):
        schema = _tool("npg_list_countries").inputSchema
        params = schema.get("properties", {})
        assert "expand" in params
        assert params["expand"].get("default") is False
        assert "expand" not in schema.get("required", [])

    def test_exempt_tool_keeps_its_own_cap(self, monkeypatch, small_cap):
        monkeypatch.setattr(
            main_mod,
            "_get_client",
            lambda: type(
                "C", (), {"get_text": lambda self, path, params=None: "L" * 5_000_000}
            )(),
        )
        out = _call("npg_download_log_file", {"filename": "access.log"})
        # 256 KB cap from main.py, not the 4 KB result cap.
        assert len(out["data"]) == main_mod._LOG_DOWNLOAD_MAX_BYTES
        assert out["total_bytes"] == 5_000_000
        assert out["truncated"] is True
        assert out["returned_bytes"] == main_mod._LOG_DOWNLOAD_MAX_BYTES
        # No result-cap metadata block: this tool owns its truncation contract.
        assert not isinstance(out["truncated"], dict)

    def test_only_expand_tools_are_instrumented(self):
        resultcap.instrument_tools(main_mod.mcp)
        wrapped = {
            tool.name
            for tool in main_mod.mcp._tool_manager.list_tools()
            if getattr(tool.fn, resultcap._WRAPPED_ATTR, False)
        }
        assert "npg_list_countries" in wrapped
        assert "npg_download_log_file" not in wrapped
        # Mutations have no result cap (their envelopes are small and their
        # payload is not agent context).
        assert "npg_create_proxy_host" not in wrapped

    def test_every_readonly_tool_declares_expand(self):
        """Drift guard: a new read-only tool without ``expand`` fails here."""
        missing = []
        for name in sorted(toolsets._discover_tool_names()):
            annotations = toolsets.annotations_for(name)
            if annotations is None:
                continue
            if not annotations.readOnlyHint:
                continue
            properties = _schema_properties(name)
            if name in resultcap.EXEMPT_TOOLS:
                assert "expand" not in properties
                continue
            if "expand" not in properties:
                missing.append(name)
        assert missing == []

    def test_no_mutating_tool_declares_expand(self):
        offenders = []
        for name in sorted(toolsets._discover_tool_names()):
            annotations = toolsets.annotations_for(name)
            if annotations is None or annotations.readOnlyHint:
                continue
            if "expand" in _schema_properties(name):
                offenders.append(name)
        assert offenders == []

    def test_instrumenting_twice_is_idempotent(self, monkeypatch, small_cap):
        monkeypatch.setattr(main_mod, "_get_client", lambda: _HugeListClient())
        resultcap.instrument_tools(main_mod.mcp)
        wrapped_once = {
            tool.name
            for tool in main_mod.mcp._tool_manager.list_tools()
            if getattr(tool.fn, resultcap._WRAPPED_ATTR, False)
        }
        assert len(wrapped_once) == 150
        assert resultcap.instrument_tools(main_mod.mcp) == 0
        wrapped_twice = {
            tool.name
            for tool in main_mod.mcp._tool_manager.list_tools()
            if getattr(tool.fn, resultcap._WRAPPED_ATTR, False)
        }
        assert wrapped_twice == wrapped_once
        out = _call("npg_list_countries", {})
        # A single cap pass: the metadata is not nested inside itself.
        assert isinstance(out["truncated"], dict)
        assert "truncated" not in out["truncated"]

    def test_instrument_tools_never_raises_on_broken_manager(self):
        class Broken:
            class _TM:
                @staticmethod
                def list_tools():
                    raise RuntimeError("nope")

            _tool_manager = _TM()

        assert resultcap.instrument_tools(Broken()) == 0

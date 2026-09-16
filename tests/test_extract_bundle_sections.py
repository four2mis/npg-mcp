"""Unit tests for _extract_bundle_sections (npg_import_proxy_host bundle parsing).

Covers the three accepted bundle shapes (full export result, bare data object,
bare sections dict) and the fail-closed rules:
* unknown top-level schema_version -> ValueError
* unknown schema_version hidden inside the sections dict -> ValueError
* missing host section -> ValueError
* non-dict bundle -> ValueError
"""

from __future__ import annotations

import pytest

from npg_mcp.main import _extract_bundle_sections

_HOST = {"forward_host": "127.0.0.1", "forward_port": 8080}


class TestExtractBundleSections:
    def test_full_export_result_shape(self):
        bundle = {
            "success": True,
            "data": {"schema_version": 1, "sections": {"host": _HOST}},
        }
        sv, sections = _extract_bundle_sections(bundle)
        assert sv == 1
        assert sections["host"] == _HOST

    def test_bare_data_shape(self):
        bundle = {"schema_version": 1, "sections": {"host": _HOST}}
        sv, sections = _extract_bundle_sections(bundle)
        assert sv == 1
        assert sections["host"] == _HOST

    def test_bare_sections_shape(self):
        sv, sections = _extract_bundle_sections({"host": _HOST})
        assert sv is None
        assert sections["host"] == _HOST

    def test_unknown_top_level_schema_version_rejected(self):
        bundle = {"schema_version": 99, "sections": {"host": _HOST}}
        with pytest.raises(ValueError, match="unsupported bundle schema_version 99"):
            _extract_bundle_sections(bundle)

    def test_schema_version_hidden_in_sections_rejected(self):
        bundle = {"sections": {"schema_version": 99, "host": _HOST}}
        with pytest.raises(ValueError, match="unsupported bundle schema_version 99"):
            _extract_bundle_sections(bundle)

    def test_schema_version_in_data_object_rejected(self):
        bundle = {"data": {"schema_version": 2, "sections": {"host": _HOST}}}
        with pytest.raises(ValueError, match="unsupported bundle schema_version 2"):
            _extract_bundle_sections(bundle)

    def test_missing_host_section_rejected(self):
        with pytest.raises(ValueError, match="host"):
            _extract_bundle_sections({"sections": {"rate_limit": {"enabled": True}}})

    def test_non_dict_bundle_rejected(self):
        with pytest.raises(ValueError, match="must be a dict"):
            _extract_bundle_sections("not-a-dict")  # type: ignore[arg-type]

    def test_sections_copy_does_not_leak_schema_version_key(self):
        # The parser must strip a sections-level schema_version from the
        # returned sections so it never leaks into skipped_sections.
        _, sections = _extract_bundle_sections(
            {"sections": {"schema_version": 1, "host": _HOST}}
        )
        assert "schema_version" not in sections
        assert sections["host"] == _HOST

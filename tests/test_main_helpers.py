"""Unit tests for npg_mcp.main helper functions.

Covers:
* _id_path — converts int/str IDs to strings for URL path interpolation.

Plus a forward-compatible test for the planned _build_body helper (owned by a
separate task). Importing npg_mcp.main is safe: it instantiates the FastMCP
object at module level but the server only starts inside ``if __name__ ==
"__main__": main()``, which never runs under pytest. No network is touched.
"""

from __future__ import annotations

import pytest

from npg_mcp.main import _id_path, _validate_id, _validate_required


class TestValidateId:
    """_validate_id must accept positive ints / non-empty strings and reject
    everything else with a clear ValueError message."""

    def test_accepts_positive_int(self):
        _validate_id("host_id", 42)  # no raise

    def test_accepts_uuid_string(self):
        _validate_id("cert_id", "a7a057e9-6b31-4780-8d66-cfb920918284")  # no raise

    def test_accepts_digit_string(self):
        _validate_id("host_id", "42")  # no raise

    def test_accepts_slug_string(self):
        _validate_id("slug", "cloudflare")  # no raise

    @pytest.mark.parametrize("bad", [None, "", "   ", 0, -7, True, False, [], {}])
    def test_rejects_invalid_values(self, bad):
        with pytest.raises(ValueError, match="host_id is required"):
            _validate_id("host_id", bad)

    def test_error_message_uses_param_name(self):
        with pytest.raises(ValueError, match="cert_id is required \\(got: empty string\\)"):
            _validate_id("cert_id", "")


class TestValidateRequired:
    """_validate_required must reject None / empty containers and accept
    non-empty values of any other type."""

    def test_accepts_non_empty_string(self):
        _validate_required("forward_host", "127.0.0.1")  # no raise

    def test_accepts_non_empty_list(self):
        _validate_required("domain_names", ["a.example.com"])  # no raise

    def test_accepts_int_and_bool(self):
        _validate_required("forward_port", 8080)  # no raise
        _validate_required("favorite", True)  # no raise

    @pytest.mark.parametrize("bad", [None, "", "   ", [], {}])
    def test_rejects_empty_values(self, bad):
        with pytest.raises(ValueError, match="domain_names is required"):
            _validate_required("domain_names", bad)

    def test_error_message_uses_param_name(self):
        with pytest.raises(ValueError, match="domain_names is required \\(got: empty string\\)"):
            _validate_required("domain_names", [])


class TestIdPath:
    """_id_path must coerce both int and str IDs to plain strings."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (123, "123"),
            (0, "0"),
            (-7, "-7"),
            ("abc", "abc"),
            ("a7a057e9-6b31-4780-8d66-cfb920918284", "a7a057e9-6b31-4780-8d66-cfb920918284"),
            ("42", "42"),
        ],
    )
    def test_coerces_int_and_str(self, value, expected):
        assert _id_path(value) == expected

    def test_returns_new_str_object(self):
        value = "abc"
        assert _id_path(value) == value
        assert isinstance(_id_path(value), str)


class TestBuildBody:
    """Forward-compatible tests for the planned _build_body helper.

    The helper is implemented by the child task t_62f8371e; until it lands,
    these tests are skipped so the suite stays green in CI.
    """

    def _helper(self):
        try:
            from npg_mcp.main import _build_body
        except ImportError:
            pytest.skip("_build_body not yet implemented (child task t_62f8371e)")
        return _build_body

    def test_skips_none_and_internal_keys(self):
        _build_body = self._helper()
        body = _build_body(
            {
                "self": object(),
                "c": object(),
                "body": {"old": True},
                "forward_scheme": "http",
                "block_normal": None,
                "enabled": True,
            },
            {"forward_scheme": "forward_scheme", "block_normal": "block_normal_access", "enabled": "enabled"},
        )
        assert body == {"forward_scheme": "http", "enabled": True}

    def test_applies_id_path_to_id_fields(self):
        _build_body = self._helper()
        body = _build_body(
            {"ssl_cert_id": "a7a057e9-6b31-4780-8d66-cfb920918284", "host_id": 42, "forward_port": 8080},
            {"ssl_cert_id": "certificate_id", "host_id": "host_id", "forward_port": "forward_port"},
            id_fields={"ssl_cert_id", "host_id"},
        )
        assert body == {
            "certificate_id": "a7a057e9-6b31-4780-8d66-cfb920918284",
            "host_id": "42",
            "forward_port": 8080,
        }

    def test_passes_lists_through_unchanged(self):
        _build_body = self._helper()
        domains = ["a.example.com", "b.example.com"]
        servers = [{"host": "10.0.0.1", "port": 8080}]
        # Mapping is var_name -> api_field_name: var upstream_servers maps to
        # API field "servers" (as in npg_update_proxy_host_upstream).
        body = _build_body(
            {"domain_names": domains, "upstream_servers": servers},
            {"domain_names": "domain_names", "upstream_servers": "servers"},
        )
        assert body == {"domain_names": domains, "servers": servers}
        assert body["domain_names"] is domains
        assert body["servers"] is servers

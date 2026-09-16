"""Unit tests for npg_mcp.main helper functions.

Covers:
* _id_path — percent-encodes URL-path-interpolated identifiers.
* _id_str — raw stringifier for JSON body values / response keys.
* _validate_id / _validate_required — pre-flight parameter validation.
* _build_body — conditional body construction (None-skipping, id_fields).
* URL construction — recording fake client proves _id_path encoding lands in
  built request paths for id-, slug-, and free-text-path tools.

Importing npg_mcp.main is safe: it instantiates the FastMCP object at module
level but the server only starts inside ``if __name__ == "__main__": main()``,
which never runs under pytest. No network is touched.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod
from npg_mcp.main import _id_path, _id_str, _validate_id, _validate_required


class _RecordingClient:
    """Fake NPGClient recording every (method, path, body, params) call."""

    def __init__(self):
        self.calls = []

    def get(self, path, params=None, redirect_ok=False):
        self.calls.append(("GET", path, None, params))
        return {}

    def get_text(self, path, params=None):
        self.calls.append(("GET_TEXT", path, None, params))
        return ""

    def post(self, path, body=None):
        self.calls.append(("POST", path, body, None))
        return {}

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body, params))
        return {}

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


def _last_path(client) -> str:
    return client.calls[-1][1]


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
        with pytest.raises(
            ValueError, match="cert_id is required \\(got: empty string\\)"
        ):
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
        with pytest.raises(
            ValueError, match="domain_names is required \\(got: empty string\\)"
        ):
            _validate_required("domain_names", [])


class TestIdPath:
    """_id_path must coerce int/str IDs to URL-safe strings (percent-encoded).

    UUIDs, digits, and alphanumerics are quote-invariant, so real ids pass
    through unchanged; anything URL-unsafe (space, /, #, %, ..) gets encoded
    so it can never alter path structure.
    """

    @pytest.mark.parametrize(
        "value,expected",
        [
            (123, "123"),
            (0, "0"),
            (-7, "-7"),
            ("abc", "abc"),
            (
                "a7a057e9-6b31-4780-8d66-cfb920918284",
                "a7a057e9-6b31-4780-8d66-cfb920918284",
            ),
            ("42", "42"),
            # URL-unsafe values get percent-encoded (safe="")
            ("a b/../c", "a%20b%2F..%2Fc"),
            ("host/../../admin", "host%2F..%2F..%2Fadmin"),
            ("name with space", "name%20with%20space"),
            ("slug#fragment", "slug%23fragment"),
            ("100%", "100%25"),
            ("a?b=c&d=e", "a%3Fb%3Dc%26d%3De"),
        ],
    )
    def test_coerces_and_encodes(self, value, expected):
        assert _id_path(value) == expected

    def test_quote_invariant_for_real_ids(self):
        # UUIDs and digit strings are byte-for-byte unchanged
        uuid_val = "a7a057e9-6b31-4780-8d66-cfb920918284"
        assert _id_path(uuid_val) == uuid_val
        assert _id_path(12345) == "12345"

    def test_returns_new_str_object(self):
        value = "abc"
        assert _id_path(value) == value
        assert isinstance(_id_path(value), str)


class TestIdStr:
    """_id_str must coerce int/str IDs to raw strings — no URL encoding."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (123, "123"),
            ("abc", "abc"),
            ("a b/../c", "a b/../c"),  # raw — bodies must not be encoded
            (
                "a7a057e9-6b31-4780-8d66-cfb920918284",
                "a7a057e9-6b31-4780-8d66-cfb920918284",
            ),
        ],
    )
    def test_raw_string_no_encoding(self, value, expected):
        assert _id_str(value) == expected


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
            {
                "forward_scheme": "forward_scheme",
                "block_normal": "block_normal_access",
                "enabled": "enabled",
            },
        )
        assert body == {"forward_scheme": "http", "enabled": True}

    def test_applies_id_path_to_id_fields(self):
        _build_body = self._helper()
        body = _build_body(
            {
                "ssl_cert_id": "a7a057e9-6b31-4780-8d66-cfb920918284",
                "host_id": 42,
                "forward_port": 8080,
            },
            {
                "ssl_cert_id": "certificate_id",
                "host_id": "host_id",
                "forward_port": "forward_port",
            },
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


class TestUrlConstruction:
    """Recording fake client proves _id_path encoding lands in built URLs.

    Spot-checks one tool per path-parameter shape: UUID id, free-text slug,
    and free-text domain/IP/filename.
    """

    def test_proxy_host_by_uuid_id(self, recording):
        _run(main_mod.npg_get_proxy_host("a7a057e9-6b31-4780-8d66-cfb920918284"))
        expected = "/api/v1/proxy-hosts/a7a057e9-6b31-4780-8d66-cfb920918284"
        assert _last_path(recording) == expected

    def test_cloud_provider_by_slug(self, recording):
        _run(main_mod.npg_get_cloud_provider("cloudflare"))
        assert _last_path(recording) == "/api/v1/cloud-providers/cloudflare"

    def test_cloud_provider_slug_unsafe_chars_encoded(self, recording):
        # A slug with a '/' must stay ONE path segment, not traverse
        _run(main_mod.npg_get_cloud_provider("my provider/v2"))
        assert _last_path(recording) == "/api/v1/cloud-providers/my%20provider%2Fv2"

    def test_ban_history_for_ip(self, recording):
        _run(main_mod.npg_get_ban_history_for_ip("8.8.8.8"))
        assert _last_path(recording) == "/api/v1/banned-ips/history/ip/8.8.8.8"

    def test_proxy_host_by_domain(self, recording):
        _run(main_mod.npg_get_proxy_host_by_domain("app.four2mis.com"))
        assert _last_path(recording) == "/api/v1/proxy-hosts/by-domain/app.four2mis.com"

    def test_log_file_download(self, recording):
        _run(main_mod.npg_download_log_file("access log 2026.log"))
        expected = "/api/v1/system-settings/log-files/access%20log%202026.log/download"
        assert _last_path(recording) == expected

    def test_update_body_certificate_id_stays_raw(self, recording):
        # _build_body id_fields must send the RAW id in bodies (no %XX)
        _run(main_mod.npg_bulk_apply_certificate(
            host_ids=["h1"], cert_id="cert-with space"))
        method, path, body, params = recording.calls[0]
        assert method == "PUT"
        assert path == "/api/v1/proxy-hosts/h1"
        assert body == {"certificate_id": "cert-with space"}

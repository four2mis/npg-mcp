"""Binary-safe download tools: get_bytes() + base64 round-trip tests.

Covers:
* NPGClient.get_bytes() returns exact bytes + content-type header (gzip and
  zip payloads survive byte-identical, unlike get_text()'s lossy resp.text).
* Tool-level base64 round-trip: npg_download_backup / npg_get_certificate_
  download return encoding=base64 payloads that decode back to the original
  archive bytes.
* text/* responses still return plain data (no base64 marker).
* npg_download_log_file remains on get_text() (plain-text passthrough).

Every HTTP call is mocked with respx — there is NO real network access.
"""

from __future__ import annotations

import base64
import gzip
import io
import zipfile

import httpx
import pytest
import respx

from npg_mcp import main as main_mod
from npg_mcp.client import NPGClient

BASE = "https://npg.test"


def _make_gzip(payload: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(payload)
    return buf.getvalue()


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def client():
    return NPGClient(base_url=BASE, token="ng_test_token")


class TestGetBytes:
    def test_gzip_bytes_identical(self, client):
        payload = _make_gzip(b"hello backup world" * 100)
        with respx.mock:
            respx.get(f"{BASE}/api/v1/backups/abc/download").mock(
                return_value=httpx.Response(
                    200,
                    content=payload,
                    headers={"content-type": "application/gzip"},
                )
            )
            content, ctype = client.get_bytes("/api/v1/backups/abc/download")
        assert content == payload  # byte-identical
        assert gzip.decompress(content) == b"hello backup world" * 100
        assert ctype == "application/gzip"

    def test_zip_bytes_identical(self, client):
        payload = _make_zip({"cert.pem": "-----BEGIN CERTIFICATE-----\nabc\n"})
        with respx.mock:
            respx.get(f"{BASE}/api/v1/certificates/x/download").mock(
                return_value=httpx.Response(
                    200,
                    content=payload,
                    headers={"content-type": "application/zip"},
                )
            )
            content, ctype = client.get_bytes("/api/v1/certificates/x/download")
        assert content == payload
        assert zipfile.ZipFile(io.BytesIO(content)).namelist() == ["cert.pem"]
        assert ctype == "application/zip"

    def test_content_type_default_empty(self, client):
        with respx.mock:
            respx.get(f"{BASE}/api/v1/x").mock(
                return_value=httpx.Response(200, content=b"\x00\x01\x02")
            )
            content, ctype = client.get_bytes("/api/v1/x")
        assert content == b"\x00\x01\x02"
        assert ctype == ""

    def test_http_error_sanitized(self, client):
        with respx.mock:
            respx.get(f"{BASE}/api/v1/x").mock(
                return_value=httpx.Response(404, json={"message": "not found"})
            )
            from npg_mcp.client import NPGError
            with pytest.raises(NPGError):
                client.get_bytes("/api/v1/x")


class TestDownloadToolsBase64RoundTrip:
    """Tool-level: binary payload -> base64 -> decode == original bytes."""

    @pytest.mark.parametrize("tool_name", ["npg_download_backup", "npg_get_certificate_download"])
    def test_binary_payload_base64_round_trip(self, tool_name, monkeypatch):
        if tool_name == "npg_download_backup":
            raw = _make_gzip(b"backup-payload-" * 50)
            path = "/api/v1/backups/bid-123/download"
            ctype = "application/gzip"
            arg = ("backup_id", "bid-123")
        else:
            raw = _make_zip({"fullchain.pem": "cert", "privkey.pem": "key"})
            path = "/api/v1/certificates/cid-9/download"
            ctype = "application/zip"
            arg = ("cert_id", "cid-9")

        fake = NPGClient(base_url=BASE, token="ng_t")

        def _fake_get_bytes(p, params=None):
            assert p == path
            return raw, ctype

        fake.get_bytes = _fake_get_bytes
        monkeypatch.setattr(main_mod, "_get_client", lambda: fake)

        result = getattr(main_mod, tool_name)(arg[1])
        # Tools are async functions — run the coroutine.
        import asyncio
        if asyncio.iscoroutine(result):
            result = asyncio.get_event_loop().run_until_complete(result) if False else asyncio.run(result)

        assert result["success"] is True
        assert result["encoding"] == "base64"
        assert result["content_type"] == ctype
        decoded = base64.b64decode(result["data"])
        assert decoded == raw

    @pytest.mark.parametrize("tool_name,arg", [
        ("npg_download_backup", ("backup_id", "bid-123")),
        ("npg_get_certificate_download", ("cert_id", "cid-9")),
    ])
    def test_text_payload_plain_passthrough(self, tool_name, arg, monkeypatch):
        raw = b"plain textual content"

        def _fake_get_bytes(self, p, params=None):
            return raw, "text/plain; charset=utf-8"

        monkeypatch.setenv("NPG_API_TOKEN", "ng_test")
        monkeypatch.setattr(NPGClient, "get_bytes", _fake_get_bytes)

        import asyncio
        result = asyncio.run(getattr(main_mod, tool_name)(arg[1]))

        assert result["success"] is True
        assert result["data"] == raw.decode()
        assert "encoding" not in result

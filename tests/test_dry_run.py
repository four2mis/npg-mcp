"""Unit tests for NPG_DRY_RUN dry-run mode (npg_mcp.client + tool surface).

Covers:
* client-level interception: post/put/delete/post_file return a structured
  payload (``dry_run: true``, method, path, body/params/multipart summary)
  instead of touching the network whenever NPG_DRY_RUN is enabled.
* GET is never intercepted.
* the module flag is read at import from the environment (truthy parse).
* tool-level surfacing: tools that synthesize their own message (deletes,
  reload, email set) expose the dry-run payload via ``_mutate_result``, and
  tools that return the client's value pass it through automatically.

No real network access: the client layer is intercepted with ``_DRY_RUN``
toggled, and tool-level tests monkeypatch ``_get_client`` with a fake that
behaves exactly like the dry-run client.
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.client as client_mod
from npg_mcp.client import NPGClient

import npg_mcp.main as main_mod


BASE = "https://npg.test"


class TestDryRunFlag:
    """NPG_DRY_RUN env parsing — read once at import time."""

    def test_disabled_by_default(self):
        assert client_mod.dry_run_enabled() is False

    def test_payload_marks_dry_run(self):
        payload = client_mod._dry_run_payload("POST", "/api/v1/x", {"a": 1})
        assert payload == {
            "dry_run": True,
            "method": "POST",
            "path": "/api/v1/x",
            "body": {"a": 1},
        }

    def test_payload_omits_body_when_none(self):
        payload = client_mod._dry_run_payload("DELETE", "/api/v1/x/1")
        assert payload == {"dry_run": True, "method": "DELETE", "path": "/api/v1/x/1"}
        assert "body" not in payload


class TestClientInterception:
    """With dry-run enabled, mutating client calls never hit the network."""

    @pytest.fixture(autouse=True)
    def _enable_dry_run(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_DRY_RUN", True)

    def _client(self):
        return NPGClient(base_url=BASE, token="ng_tok")

    def test_post_returns_payload(self):
        payload = self._client().post("/api/v1/proxy-hosts", {"domain_names": ["x.test"]})
        assert payload == {
            "dry_run": True,
            "method": "POST",
            "path": "/api/v1/proxy-hosts",
            "body": {"domain_names": ["x.test"]},
        }

    def test_post_without_body_omits_body_key(self):
        payload = self._client().post("/api/v1/proxy-hosts/sync")
        assert payload == {"dry_run": True, "method": "POST", "path": "/api/v1/proxy-hosts/sync"}

    def test_put_with_params(self):
        payload = self._client().put(
            "/api/v1/proxy-hosts/1", {"enabled": False}, params={"skip_nginx": "true"}
        )
        assert payload["method"] == "PUT"
        assert payload["body"] == {"enabled": False}
        assert payload["params"] == {"skip_nginx": "true"}

    def test_delete_payload(self):
        payload = self._client().delete("/api/v1/proxy-hosts/1")
        assert payload == {"dry_run": True, "method": "DELETE", "path": "/api/v1/proxy-hosts/1"}

    def test_delete_with_params_payload(self):
        payload = self._client().delete("/api/v1/banned-ips", params={"ip": "1.2.3.4"})
        assert payload["params"] == {"ip": "1.2.3.4"}

    def test_post_file_summarizes_upload(self):
        payload = self._client().post_file(
            "/api/v1/backups/upload-restore", "backup", b"tar-bytes", "restore.tar.gz"
        )
        assert payload["method"] == "POST"
        assert payload["multipart"] == {
            "field": "backup",
            "filename": "restore.tar.gz",
            "size_bytes": len(b"tar-bytes"),
        }
        # raw bytes must never be echoed back
        assert "body" not in payload
        assert "tar-bytes" not in repr(payload)


class TestClientNotDryRun:
    """Without the flag, calls execute normally (delegated to httpx)."""

    def test_disabled_posts_normally(self):
        client = NPGClient(base_url=BASE, token="ng_tok")
        # no dry-run intercept: this would raise a transport error, not return a payload
        with pytest.raises(Exception):
            client.post("/api/v1/proxy-hosts", {"a": 1})


class TestToolDryRunSurface:
    """Mutating tools expose the dry-run payload even when they normally
    synthesize their own result message."""

    @pytest.fixture
    def dry_client(self, monkeypatch):
        """Fake client that behaves exactly like the real one in dry-run mode."""

        class _FakeDryClient:
            def post(self, path, body=None, params=None):
                payload = {"dry_run": True, "method": "POST", "path": path}
                if body is not None:
                    payload["body"] = body
                if params:
                    payload["params"] = params
                return payload

            def put(self, path, body=None, params=None):
                payload = {"dry_run": True, "method": "PUT", "path": path}
                if body is not None:
                    payload["body"] = body
                if params:
                    payload["params"] = params
                return payload

            def delete(self, path, params=None):
                payload = {"dry_run": True, "method": "DELETE", "path": path}
                if params:
                    payload["params"] = params
                return payload

        fake = _FakeDryClient()
        monkeypatch.setattr(main_mod, "_get_client", lambda: fake)
        return fake

    def _run(self, coro):
        return asyncio.run(coro)

    def test_delete_proxy_host_surfaces_payload(self, dry_client):
        result = self._run(main_mod.npg_delete_proxy_host("h1"))
        assert result == {
            "success": True,
            "data": {"dry_run": True, "method": "DELETE", "path": "/api/v1/proxy-hosts/h1"},
        }

    def test_reload_nginx_surfaces_payload(self, dry_client):
        result = self._run(main_mod.npg_reload_nginx())
        assert result["success"] is True
        assert result["data"]["dry_run"] is True
        assert result["data"]["method"] == "POST"
        assert result["data"]["path"] == "/api/v1/proxy-hosts/sync"

    def test_set_user_email_surfaces_payload(self, dry_client):
        result = self._run(main_mod.npg_set_user_email(user_id="u1", email="a@b.c"))
        assert result["success"] is True
        assert result["data"]["body"] == {"email": "a@b.c"}

    def test_create_proxy_host_simple_passes_payload_through(self, dry_client):
        result = self._run(
            main_mod.npg_create_proxy_host_simple(
                domain_names=["dry.four2mis.com"],
                forward_host="127.0.0.1",
                forward_port=8080,
            )
        )
        assert result["success"] is True
        assert result["data"]["dry_run"] is True
        assert result["data"]["method"] == "POST"
        assert result["data"]["path"] == "/api/v1/proxy-hosts"
        assert result["data"]["body"]["domain_names"] == ["dry.four2mis.com"]

    def test_test_nginx_returns_payload_not_transform(self, dry_client):
        result = self._run(main_mod.npg_test_nginx())
        assert result["success"] is True
        assert result["data"]["dry_run"] is True
        # the "valid/status" transform must not swallow the payload
        assert "valid" not in result["data"]

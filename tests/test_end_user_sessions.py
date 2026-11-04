"""Unit tests for npg_end_user_sessions result shape.

The NPG API answers ``POST /users/{id}/end-sessions`` with 204 No Content, so
``client.post()`` returns ``None``. The tool must still return a human-readable
``message`` (delete-family convention) instead of ``{"success": True,
"data": None}``.

Monkeypatches npg_mcp.main._get_client with a recording fake so the tool's real
code path runs end to end (validation -> HTTP call -> result shape).
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod

_USER_ID = "123e4567-e89b-12d3-a456-426614174000"


class _RecordingClient:
    """Fake NPGClient whose post returns an empty 204-style body."""

    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        return self.payload


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


class TestEndUserSessionsShape:
    def test_204_returns_message_not_null_data(self, recording):
        result = _run(main_mod.npg_end_user_sessions(user_id=_USER_ID))
        assert result == {
            "success": True,
            "message": f"Ended all sessions for user {_USER_ID}",
        }
        assert recording.calls == [
            ("POST", f"/api/v1/users/{_USER_ID}/end-sessions", None)
        ]

    def test_slash_in_id_is_path_encoded(self, recording):
        result = _run(main_mod.npg_end_user_sessions(user_id="abc/def"))
        assert result["success"] is True
        assert result["message"].endswith("abc/def")
        expected = ("POST", "/api/v1/users/abc%2Fdef/end-sessions", None)
        assert recording.calls == [expected]

    def test_missing_user_id_is_clean_error(self, recording):
        result = _run(main_mod.npg_end_user_sessions(user_id=""))
        assert result["success"] is False
        assert recording.calls == []

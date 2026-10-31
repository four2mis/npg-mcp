"""Unit tests for the CAPTCHA verify body and challenge-config params.

Covers, without any network access (recording fake client):
* ``npg_verify_challenge`` — the request body mirrors upstream
  ``model.VerifyCaptchaRequest`` (``token`` / ``proxy_host_id`` /
  ``challenge_reason``); the phantom ``solution`` field is gone, and an
  upstream ``{"success": false}`` is surfaced as an envelope ``success:
  false`` instead of being reported as a successful call.
* ``npg_update_proxy_host_challenge`` — ``secret_key`` / ``page_message`` /
  ``theme`` reach the API and stay partial (omitted fields are never sent).
"""

from __future__ import annotations

import asyncio

import pytest

import npg_mcp.main as main_mod


class _RecordingClient:
    def __init__(self, post_result=None):
        self.calls = []
        self.post_result = post_result if post_result is not None else {"ok": True}

    def post(self, path, body=None, params=None):
        self.calls.append(("POST", path, body))
        return self.post_result

    def put(self, path, body=None, params=None):
        self.calls.append(("PUT", path, body))
        return {"success": True}


@pytest.fixture
def recording(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(main_mod, "_get_client", lambda: client)
    return client


def _run(coro):
    return asyncio.run(coro)


def _last_body(recording):
    method, path, body = recording.calls[-1]
    assert method in ("POST", "PUT")
    return body


class TestVerifyChallengeBody:
    def test_token_only_body(self, recording):
        _run(main_mod.npg_verify_challenge(token="tok"))
        assert _last_body(recording) == {"token": "tok"}

    def test_proxy_host_id_and_reason_are_sent(self, recording):
        _run(
            main_mod.npg_verify_challenge(
                token="tok",
                proxy_host_id="d8e49511-299a-4f5c-a07d-49fa726e766d",
                challenge_reason="bot_filter",
            )
        )
        assert _last_body(recording) == {
            "token": "tok",
            "proxy_host_id": "d8e49511-299a-4f5c-a07d-49fa726e766d",
            "challenge_reason": "bot_filter",
        }

    def test_no_solution_field_is_ever_sent(self, recording):
        _run(main_mod.npg_verify_challenge(token="tok", proxy_host_id="abc"))
        assert "solution" not in _last_body(recording)

    def test_empty_token_is_rejected_before_any_call(self, recording):
        result = _run(main_mod.npg_verify_challenge(token="   "))
        assert result["success"] is False
        assert "token" in result["error"]
        assert recording.calls == []


class TestVerifyChallengeEnvelope:
    def test_upstream_success_false_becomes_envelope_failure(self, monkeypatch):
        client = _RecordingClient(
            post_result={"success": False, "error": "CAPTCHA verification failed"}
        )
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        result = _run(main_mod.npg_verify_challenge(token="tok"))
        assert result["success"] is False
        assert result["error"] == "CAPTCHA verification failed"
        assert result["data"]["success"] is False

    def test_upstream_success_true_stays_successful(self, monkeypatch):
        client = _RecordingClient(
            post_result={"success": True, "token": "bypass", "expires_in": 86400}
        )
        monkeypatch.setattr(main_mod, "_get_client", lambda: client)
        result = _run(main_mod.npg_verify_challenge(token="tok"))
        assert result["success"] is True
        assert result["data"]["token"] == "bypass"


class TestUpdateChallengeConfig:
    def test_new_fields_are_sent(self, recording):
        _run(
            main_mod.npg_update_proxy_host_challenge(
                host_id="abc",
                secret_key="1x0000000000000000000000000000000AA",
                page_message="checking your browser",
                theme="dark",
            )
        )
        assert _last_body(recording) == {
            "secret_key": "1x0000000000000000000000000000000AA",
            "page_message": "checking your browser",
            "theme": "dark",
        }

    def test_fields_combine_with_existing_params(self, recording):
        _run(
            main_mod.npg_update_proxy_host_challenge(
                host_id="abc",
                enabled=True,
                challenge_type="turnstile",
                site_key="1x00000000000000000000AA",
                secret_key="secret",
                token_validity=600,
                min_score=0.5,
                apply_to="both",
                page_title="title",
                page_message="msg",
                theme="light",
            )
        )
        assert _last_body(recording) == {
            "enabled": True,
            "challenge_type": "turnstile",
            "site_key": "1x00000000000000000000AA",
            "secret_key": "secret",
            "token_validity": 600,
            "min_score": 0.5,
            "apply_to": "both",
            "page_title": "title",
            "page_message": "msg",
            "theme": "light",
        }

    def test_omitted_fields_stay_partial(self, recording):
        _run(main_mod.npg_update_proxy_host_challenge(host_id="abc", theme="dark"))
        assert _last_body(recording) == {"theme": "dark"}

    def test_body_goes_to_the_challenge_route(self, recording):
        _run(main_mod.npg_update_proxy_host_challenge(host_id="abc", theme="dark"))
        method, path, _ = recording.calls[-1]
        assert (method, path) == ("PUT", "/api/v1/proxy-hosts/abc/challenge")


class TestVerifyChallengeDescription:
    def _description(self):
        tool = asyncio.run(main_mod.mcp.list_tools())
        for t in tool:
            if t.name == "npg_verify_challenge":
                return t.description
        raise AssertionError("npg_verify_challenge not registered")

    def test_description_omits_solution_and_names_proxy_host_id(self):
        desc = self._description()
        assert "solution" not in desc
        assert "proxy_host_id" in desc
        assert "challenge_reason" in desc

    def test_description_within_cap(self):
        assert len(self._description()) <= 460

"""NginxProxyGuard API client — thin HTTP wrapper with JWT auth."""

from __future__ import annotations

import os
from contextvars import ContextVar
from urllib.parse import urljoin

import httpx

# Per-request token store — scoped to the current request context var so
# concurrent clients cannot overwrite each other's session token.
_request_token: ContextVar[str] = ContextVar("npg_request_token", default="")
_current_base_url: str = ""


def set_token(token: str) -> None:
    """Set the token for the *current* request context (not process-wide)."""
    _request_token.set(token)


def get_token() -> str:
    return _request_token.get()


def set_base_url(base_url: str) -> None:
    global _current_base_url
    _current_base_url = base_url


def get_base_url() -> str:
    return _current_base_url or os.environ.get("NPG_BASE_URL", "http://npg-api:8080")


class NPGError(Exception):
    """Sanitized error — never contains internal URLs, hostnames, or tracebacks."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NPGClient:
    """Thin httpx wrapper over NPG API with JWT session auth."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self._token = token or get_token()
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=30,
        )

    def _sanitize(self, exc: Exception) -> NPGError:
        """Convert a transport/HTTP exception into a sanitized NPGError."""
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            return NPGError(f"NPG API returned HTTP {status}")
        return NPGError("NPG API request failed")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def get(self, path: str, params: dict | None = None) -> dict | None:
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            resp = self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._sanitize(e) from e

    def post(self, path: str, body: dict | None = None, params: dict | None = None) -> dict:
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            resp = self._client.post(
                url, json=body, params=params, headers=self._headers()
            )
            resp.raise_for_status()
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._sanitize(e) from e

    def put(self, path: str, body: dict | None = None, params: dict | None = None) -> dict:
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            resp = self._client.put(
                url, json=body, params=params, headers=self._headers()
            )
            resp.raise_for_status()
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._sanitize(e) from e

    def delete(self, path: str, params: dict | None = None) -> dict | None:
        try:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            resp = self._client.delete(url, params=params, headers=self._headers())
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except NPGError:
            raise
        except Exception as e:
            raise self._sanitize(e) from e

    def login(self, username: str, password: str, tfa_code: str | None = None) -> dict:
        """Authenticate and return JWT token."""
        try:
            body = {"username": username, "password": password}
            if tfa_code:
                body["tfa_code"] = tfa_code
            resp = self._client.post(
                urljoin(self.base_url + "/api/v1/", "auth/login"), json=body
            )
            resp.raise_for_status()
            data = resp.json()
            token = data["token"]
            self._token = token
            set_token(token)
            self._client.headers["Authorization"] = f"Bearer {token}"
            return data
        except NPGError:
            raise
        except Exception as e:
            raise self._sanitize(e) from e

    def logout(self) -> dict:
        """Invalidate current session."""
        result = self.post("/api/v1/auth/logout")
        set_token("")
        return result

    def me(self) -> dict | None:
        """Get current user info."""
        return self.get("/api/v1/auth/me")

    def close(self) -> None:
        self._client.close()

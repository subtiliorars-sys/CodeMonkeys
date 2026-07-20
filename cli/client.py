"""Thin REST client for the CodeMonkeys session/agent-loop API.

Mirrors the request/response shapes `static/forge/app.js`'s `api()` helper
already relies on (see `server.py`'s `/api/sessions*` routes) — this is a new
*client* of that existing, already-audited API surface, not a new API.
"""
from __future__ import annotations

import requests


class ApiError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _request(self, method: str, path: str, json: dict | None = None, params: dict | None = None) -> dict:
        r = requests.request(
            method, self.base_url + path,
            headers=self._headers(), json=json, params=params, timeout=self.timeout,
        )
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not r.ok:
            raise ApiError(data.get("detail") or f"{r.status_code} {r.reason}")
        return data

    # ---- auth ----
    def login(self, username: str, mfa_code: str = "") -> dict:
        data = self._request("POST", "/api/login", json={"username": username, "mfa_code": mfa_code})
        self.token = data["token"]
        return data

    # ---- sessions ----
    def create_session(self, title: str = "", repo: str = "", budget_usd: float | None = None) -> dict:
        return self._request("POST", "/api/sessions", json={"title": title, "repo": repo, "budget_usd": budget_usd})

    def list_sessions(self) -> list:
        return self._request("GET", "/api/sessions")["sessions"]

    def send_message(self, sid: str, text: str, mode: str = "default", files: list | None = None) -> dict:
        return self._request(
            "POST", f"/api/sessions/{sid}/message",
            json={"text": text, "mode": mode, "files": files or []},
        )

    def events(self, sid: str, after: int = -1) -> dict:
        return self._request("GET", f"/api/sessions/{sid}/events", params={"after": after})

    def approve(self, sid: str, approval_id: str, approve: bool) -> dict:
        return self._request("POST", f"/api/sessions/{sid}/approve", json={"approval_id": approval_id, "approve": approve})

    def stop(self, sid: str) -> dict:
        return self._request("POST", f"/api/sessions/{sid}/stop")

    def resume(self, sid: str) -> dict:
        return self._request("POST", f"/api/sessions/{sid}/resume")

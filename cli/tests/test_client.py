"""cli.client — requests-mocked tests (no server process needed).

Run: ./.venv/bin/python -m pytest cli/tests/ -q
"""
import pytest

from cli.client import ApiError, Client


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self.reason = "error" if status_code >= 400 else "OK"
        self.ok = status_code < 400
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


@pytest.fixture
def client():
    return Client("http://127.0.0.1:8000", token="tok123")


def test_login_stores_token(monkeypatch):
    c = Client("http://127.0.0.1:8000")

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        assert method == "POST"
        assert url.endswith("/api/login")
        assert "Authorization" not in headers
        return FakeResponse(200, {"token": "abc", "username": "boss", "role": "Owner"})

    monkeypatch.setattr("cli.client.requests.request", fake_request)
    data = c.login("boss", "123456")
    assert data["username"] == "boss"
    assert c.token == "abc"


def test_send_message_uses_bearer_auth(monkeypatch, client):
    seen = {}

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        seen["headers"] = headers
        seen["json"] = json
        assert url.endswith("/api/sessions/sid1/message")
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr("cli.client.requests.request", fake_request)
    client.send_message("sid1", "hello", mode="default")
    assert seen["headers"]["Authorization"] == "Bearer tok123"
    assert seen["json"]["text"] == "hello"


def test_events_pagination_params(monkeypatch, client):
    seen = {}

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        seen["params"] = params
        return FakeResponse(200, {"events": [{"type": "done"}], "next": 5, "status": "idle"})

    monkeypatch.setattr("cli.client.requests.request", fake_request)
    data = client.events("sid1", after=3)
    assert seen["params"] == {"after": 3}
    assert data["next"] == 5


def test_error_response_raises_api_error(monkeypatch, client):
    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        return FakeResponse(409, {"detail": "Session is busy"})

    monkeypatch.setattr("cli.client.requests.request", fake_request)
    with pytest.raises(ApiError, match="Session is busy"):
        client.send_message("sid1", "hi")


def test_approve_sends_decision(monkeypatch, client):
    seen = {}

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        seen["json"] = json
        assert url.endswith("/api/sessions/sid1/approve")
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr("cli.client.requests.request", fake_request)
    client.approve("sid1", "appr-1", True)
    assert seen["json"] == {"approval_id": "appr-1", "approve": True}

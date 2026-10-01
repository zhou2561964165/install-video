from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit(monkeypatch):
    # 限流窗口是进程级 dict，跨测试累积；每条测试前重置，避免误触发 429
    monkeypatch.setattr("app.main._window", defaultdict(list))


def _register(email, password="password123"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def test_register_returns_token_and_normalized_email():
    r = _register("New.User@Example.com")
    assert r.status_code == 200
    data = r.json()
    assert data["token"]
    assert data["user"]["email"] == "new.user@example.com"  # 小写归一


def test_login_success_and_me():
    email = "login@example.com"
    assert _register(email).status_code == 200
    r = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200
    token = r.json()["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["email"] == email
    assert body["quota"]["used"] == 0
    assert body["quota"]["remaining"] == body["quota"]["limit"]


def test_login_wrong_password_401():
    email = "badpw@example.com"
    assert _register(email).status_code == 200
    r = client.post("/api/auth/login", json={"email": email, "password": "wrongwrong"})
    assert r.status_code == 401
    assert r.json()["detail"]["error_type"] == "login_required"


def test_duplicate_email_409():
    email = "dup@example.com"
    assert _register(email).status_code == 200
    r = _register(email)
    assert r.status_code == 409


def test_register_short_password_400():
    r = _register("short@example.com", password="short")
    assert r.status_code == 400


def test_register_bad_email_400():
    r = _register("not-an-email")
    assert r.status_code == 400


def test_me_with_bad_token_401():
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["detail"]["error_type"] == "login_required"


def test_me_without_token_401():
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"]["error_type"] == "login_required"

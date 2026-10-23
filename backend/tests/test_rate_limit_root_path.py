from collections import defaultdict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import rate_limit_middleware


@pytest.fixture
def limited_app(monkeypatch):
    """Exercise the real middleware without auth, providers, or application routes."""
    monkeypatch.setattr("app.main._settings_rate_limit", 1)
    monkeypatch.setattr("app.main._window", defaultdict(list))
    app = FastAPI()
    app.middleware("http")(rate_limit_middleware)

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    def probe(path: str):
        return {"ok": True}

    return app


@pytest.mark.parametrize(
    ("root_path", "path"),
    [("", "/api/probe"), ("/demo", "/demo/api/probe"), ("/demo", "/api/probe")],
)
def test_api_rate_limit_with_root_path(limited_app, root_path, path):
    with TestClient(limited_app, root_path=root_path) as client:
        assert client.get(path).status_code == 200
        limited = client.get(path)
        assert limited.status_code == 429
        assert limited.json()["detail"]["error_type"] == "quota"


@pytest.mark.parametrize(
    ("root_path", "path", "api_path"),
    [
        ("", "/api/billing/webhook", "/api/probe"),
        ("/demo", "/demo/api/billing/webhook", "/demo/api/probe"),
        ("/demo", "/api/billing/webhook", "/api/probe"),
    ],
)
def test_webhook_stays_exempt_without_consuming_limit(limited_app, root_path, path, api_path):
    with TestClient(limited_app, root_path=root_path) as client:
        assert client.post(path).status_code == 200
        assert client.post(path).status_code == 200
        assert client.get(api_path).status_code == 200
        assert client.get(api_path).status_code == 429
        assert client.post(path).status_code == 200


@pytest.mark.parametrize("path", ["/demonstration/api/probe", "/demo/apiary/probe", "/demo/"])
def test_root_path_requires_complete_path_segment(limited_app, path):
    with TestClient(limited_app, root_path="/demo") as client:
        assert client.get(path).status_code == 200
        assert client.get(path).status_code == 200


def test_only_exact_webhook_path_is_exempt(limited_app):
    with TestClient(limited_app, root_path="/demo") as client:
        path = "/demo/api/billing/webhook/extra"
        assert client.post(path).status_code == 200
        assert client.post(path).status_code == 429

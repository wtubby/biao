"""CORS 白名单配置测试。"""

from fastapi.testclient import TestClient

from config import API_PORT, get_cors_origins
from main import app

client = TestClient(app)


def test_cors_default_origins_match_api_port():
    origins = get_cors_origins()
    assert f"http://localhost:{API_PORT}" in origins
    assert f"http://127.0.0.1:{API_PORT}" in origins
    assert "http://evil.com" not in origins


def test_cors_allows_whitelisted_origin():
    origin = f"http://localhost:{API_PORT}"
    res = client.get("/api/health", headers={"Origin": origin})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin


def test_cors_rejects_unknown_origin():
    res = client.get("/api/health", headers={"Origin": "http://evil.com"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") is None


def test_cors_preflight_rejects_unknown_origin():
    res = client.options(
        "/api/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") is None

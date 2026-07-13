"""调试 API：缓存统计等。"""

from fastapi.testclient import TestClient

from llm.llm_client import reset_cache_usage_stats
from main import app

client = TestClient(app)


def test_cache_stats_defaults_to_zero():
    reset_cache_usage_stats()
    resp = client.get("/api/debug/cache-stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prompt_cache_hit_tokens"] == 0
    assert data["prompt_cache_miss_tokens"] == 0
    assert data["requests"] == 0
    assert data["hit_rate"] is None


def test_cache_stats_reset():
    reset_cache_usage_stats()
    resp = client.post("/api/debug/cache-stats/reset")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

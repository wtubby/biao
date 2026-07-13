"""运行时可观测性：LLM 缓存统计等。"""

from fastapi import APIRouter

from llm.llm_client import get_cache_usage_stats, reset_cache_usage_stats

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/cache-stats")
def read_cache_stats():
    """DeepSeek 等 API 返回的 prompt 前缀缓存累计命中（进程内统计）。"""
    stats = get_cache_usage_stats()
    hit = stats.get("prompt_cache_hit_tokens", 0)
    miss = stats.get("prompt_cache_miss_tokens", 0)
    total = hit + miss
    hit_rate = round(hit / total, 4) if total > 0 else None
    return {
        **stats,
        "hit_rate": hit_rate,
    }


@router.post("/cache-stats/reset")
def reset_cache_stats():
    """清零进程内缓存统计（便于分段观察单次批量生成）。"""
    reset_cache_usage_stats()
    return {"success": True}

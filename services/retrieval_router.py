"""自适应 RAG 路由：按章节复杂度选择 top_k 与检索策略。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from config import (
    BM25_TOP_K,
    ENABLE_ADAPTIVE_RAG,
    KEY_CHAPTER_MIN_SCORE,
    LONG_CHAPTER_MIN_KEY_POINTS,
    LONG_CHAPTER_WORD_THRESHOLD,
    RETRIEVAL_TOP_K_DEEP,
    RETRIEVAL_TOP_K_LIGHT,
    RETRIEVAL_TOP_K_PLAN_FOLLOWUP,
)
from services.writing_guidance import is_descriptive_chapter

RetrievalMode = Literal["light", "standard", "deep", "plan_followup"]


@dataclass(frozen=True)
class RetrievalRoute:
    mode: RetrievalMode
    top_k: int
    use_vector: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "top_k": self.top_k,
            "use_vector": self.use_vector,
            "reason": self.reason,
        }


def _requirement_score(requirements: list) -> float:
    return sum(float(getattr(r, "score_value", 0) or 0) for r in (requirements or []))


def _is_complex_chapter(
    chapter_title: str,
    requirements: list,
    guidance: dict | None,
    content_plan: dict | None,
) -> tuple[bool, str]:
    title = chapter_title or ""
    score = _requirement_score(requirements)
    target_words = int((guidance or {}).get("target_words") or 0)
    key_points = [
        str(p).strip()
        for p in ((content_plan or {}).get("key_points") or [])
        if str(p).strip()
    ]

    if score >= KEY_CHAPTER_MIN_SCORE:
        return True, f"评分项分值合计 {score:g} ≥ {KEY_CHAPTER_MIN_SCORE:g}"
    if target_words >= LONG_CHAPTER_WORD_THRESHOLD:
        return True, f"目标字数 {target_words} ≥ {LONG_CHAPTER_WORD_THRESHOLD}"
    if len(key_points) >= LONG_CHAPTER_MIN_KEY_POINTS:
        return True, f"规划要点 {len(key_points)} 条 ≥ {LONG_CHAPTER_MIN_KEY_POINTS}"
    complex_keywords = ("施工方案", "技术方案", "施工组织", "专项方案", "进度计划")
    if any(kw in title for kw in complex_keywords) and score >= 3:
        return True, f"方案类章节且评分 {score:g} ≥ 3"
    return False, ""


def resolve_retrieval_route(
    *,
    chapter_title: str,
    requirements: list | None = None,
    guidance: dict | None = None,
    content_plan: dict | None = None,
    is_plan_followup: bool = False,
) -> RetrievalRoute:
    """规则路由：描述类轻检索，复杂工艺加深检索，规划二次检索收窄 top_k。"""
    if not ENABLE_ADAPTIVE_RAG:
        return RetrievalRoute(
            mode="standard",
            top_k=BM25_TOP_K,
            use_vector=True,
            reason="自适应 RAG 已关闭，使用默认混合检索",
        )

    if is_plan_followup:
        return RetrievalRoute(
            mode="plan_followup",
            top_k=RETRIEVAL_TOP_K_PLAN_FOLLOWUP,
            use_vector=True,
            reason="写作规划二次检索",
        )

    if is_descriptive_chapter(chapter_title):
        return RetrievalRoute(
            mode="light",
            top_k=RETRIEVAL_TOP_K_LIGHT,
            use_vector=False,
            reason="概况/目标类章节，轻量 BM25",
        )

    complex_chapter, complex_reason = _is_complex_chapter(
        chapter_title,
        requirements or [],
        guidance,
        content_plan,
    )
    if complex_chapter:
        return RetrievalRoute(
            mode="deep",
            top_k=RETRIEVAL_TOP_K_DEEP,
            use_vector=True,
            reason=complex_reason,
        )

    return RetrievalRoute(
        mode="standard",
        top_k=BM25_TOP_K,
        use_vector=True,
        reason="常规技术章节",
    )

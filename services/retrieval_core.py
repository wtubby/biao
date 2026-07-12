"""检索核心算法（BM25 RRF 融合、分词），供 retrieval / knowledge / reference_bid 共用。"""

from __future__ import annotations

import jieba

from config import RETRIEVAL_RRF_K


def tokenize(text: str) -> list[str]:
    return [w for w in jieba.lcut(text) if w.strip()]


def rrf_merge(rank_lists: list[list[int]], k: int | None = None) -> list[int]:
    """rank_lists: 每个是按分数降序排列的 index 列表。返回融合后的 index 排序。"""
    k = RETRIEVAL_RRF_K if k is None else k
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for pos, idx in enumerate(ranks):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + pos + 1)
    return sorted(scores.keys(), key=lambda i: scores[i], reverse=True)

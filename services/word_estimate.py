"""标书字数与页数估算。"""

from __future__ import annotations

from config import TARGET_PAGES_DEFAULT, WORDS_PER_SCORE_PAGE

WORDS_PER_PAGE = WORDS_PER_SCORE_PAGE


def estimate_from_leaves(
    leaves: list[dict],
    target_pages: int = TARGET_PAGES_DEFAULT,
    *,
    custom_word_count: bool = False,
    custom_total_words: int | None = None,
) -> dict:
    leaf_words = [int(leaf.get("target_words") or 0) for leaf in leaves]
    leaf_sum = sum(leaf_words)

    if custom_word_count and custom_total_words and custom_total_words > 0:
        total_words = int(custom_total_words)
        estimated_pages = max(1, round(total_words / WORDS_PER_PAGE)) if total_words > 0 else target_pages
    else:
        # 非自定义时以目标页数为准，避免叶子字数因历史重复分配而显示离谱
        estimated_pages = max(1, int(target_pages))
        total_words = int(estimated_pages * WORDS_PER_PAGE)
        if total_words <= 0 and leaf_sum > 0:
            total_words = leaf_sum
            estimated_pages = max(1, round(total_words / WORDS_PER_PAGE))

    return {
        "total_words": total_words,
        "estimated_pages": estimated_pages,
        "target_pages": target_pages,
        "leaf_count": len(leaves),
        "leaf_words_sum": leaf_sum,
        "words_per_page": WORDS_PER_PAGE,
    }


def format_word_count_display(total_words: int) -> str:
    if total_words >= 10000:
        return f"{(total_words / 10000):.2f}万字"
    return f"{total_words}字"

"""字数权重与检索统计相关单测。"""

from db.models import TechOutline
from services.generation_service import _summarize_retrieval_stats
from services.writing_guidance import get_word_budget_weight


def test_word_budget_weight_by_chapter_type():
    assert get_word_budget_weight("质量目标") == 0.5
    assert get_word_budget_weight("工程概况") == 0.65
    assert get_word_budget_weight("设计范围") == 0.7
    assert get_word_budget_weight("组织机构") == 0.85
    assert get_word_budget_weight("主变吊装工艺") == 1.15
    assert get_word_budget_weight("一般章节") == 1.0


def test_summarize_retrieval_stats_zero_hit_ratio():
    leaves = [
        TechOutline(
            id="1", title="设计范围", is_leaf=1,
            prompt_debug='{"retrieval_hit_count":0,"retrieval_empty_reason":"no_match"}',
        ),
        TechOutline(
            id="2", title="吊装工艺", is_leaf=1,
            prompt_debug='{"retrieval_hit_count":3}',
        ),
        TechOutline(
            id="3", title="无快照", is_leaf=1, prompt_debug=None,
        ),
    ]
    stats = _summarize_retrieval_stats(leaves)
    assert stats["total"] == 3
    assert stats["zero_hit"] == 1
    assert stats["with_hits"] == 1
    assert stats["unknown"] == 1
    assert stats["empty_reasons"]["no_match"] == 1
    assert "设计范围" in stats["zero_hit_samples"]

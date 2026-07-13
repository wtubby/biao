"""bundle 提示词块单元测试。"""

from prompts.bundle_blocks import (
    format_immediate_prior_sibling_block,
    format_prior_chapters_block,
    format_retrieval_notes,
    truncate_reference_bid,
)
from services.reference_bid_service import REFERENCE_BID_CHAPTER_LIMIT


def test_format_prior_chapters_prefers_prior_over_last_summary():
    block = format_prior_chapters_block(
        {
            "prior_summaries": ["「施工部署」已写现场布置"],
            "last_summary": "上章已写主变吊装工艺",
        },
        style="writer",
    )
    assert "前序章节已写要点" in block
    assert "施工部署" in block
    assert "上一章技术摘要" not in block
    assert "主变吊装" not in block


def test_format_prior_chapters_falls_back_to_last_summary():
    block = format_prior_chapters_block(
        {"last_summary": "上章已写主变吊装工艺"},
        style="plan",
    )
    assert "avoid 字段须据此列出勿重复点" in block
    assert "主变吊装" in block


def test_format_retrieval_notes_merges_hint_and_warning():
    note = format_retrieval_notes(
        {
            "empty_retrieval_hint": "本节无可用检索素材",
            "retrieval_warning": "当前项目领域为市政工程，建议人工核查",
        }
    )
    assert "检索说明" in note
    assert "本节无可用检索素材" in note
    assert "市政工程" in note


def test_format_retrieval_notes_adds_source_rule_when_chunks_present():
    note = format_retrieval_notes(
        {
            "retrieval_text": "[来源：资料/note.txt]\nGIS 安装工艺要求",
        }
    )
    assert "素材已标注来源" in note
    assert "无来源标签" in note


def test_truncate_reference_bid_uses_service_limit():
    text = "参" * (REFERENCE_BID_CHAPTER_LIMIT + 100)
    result = truncate_reference_bid(text)
    assert len(result) == REFERENCE_BID_CHAPTER_LIMIT
    assert "系统已截断后续参考内容" in result


def test_format_immediate_prior_sibling_block():
    block = format_immediate_prior_sibling_block(
        {
            "immediate_prior_sibling_title": "施工流水段划分",
            "immediate_prior_sibling_body": "A区、B区流水段划分如下……",
            "chapter_title": "劳动力配置计划",
        },
        style="writer",
    )
    assert "已知前情" in block
    assert "施工流水段划分" in block
    assert "A区、B区" in block
    assert "劳动力配置计划" in block
    assert "综上所述" in block
    for line in block.splitlines():
        if line.strip():
            assert not line.startswith("    "), f"unexpected indent: {line!r}"


def test_truncate_reference_bid_falls_back_to_min_suffix_when_limit_too_small():
    text = "参" * 100
    result = truncate_reference_bid(text, limit=10)
    assert result == "参" * 7 + "..."
    assert len(result) == 10


def test_format_prior_skips_last_summary_when_sibling_body_present():
    block = format_prior_chapters_block(
        {
            "last_summary": "上章已写主变吊装工艺",
            "immediate_prior_sibling_body": "上一同级正文",
            "immediate_prior_sibling_title": "流水段",
        },
        style="writer",
    )
    assert block == ""

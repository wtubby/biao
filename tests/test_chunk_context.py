"""Chunk 上下文前缀与共享 project 前缀测试。"""

from prompts.project_context import build_cacheable_project_prefix
from prompts.qa_prompt import build_qa_user_messages
from prompts.writer_prompt import build_writer_user_messages
from services.chunk_context import (
    build_chunk_context_prefix,
    chunk_display_text,
    chunk_embed_text,
)


def _sample_bundle():
    return {
        "global_params": {"工程名称": "测试工程", "电压等级": "220kV"},
        "project_overview": "四川某变电站工程。",
        "global_facts_text": "【工期】180日历天",
        "standards_hint": "按电力施工惯例",
        "contradictions": [],
        "requirements_text": "施工组织要求",
        "retrieval_text": "GIS安装工艺",
        "chapter_title": "施工方案",
        "chapter_path": "技术方案 > 施工方案",
        "guidance": {"brief": "写方案", "content_boundary": "只写施工"},
        "other_leaf_titles": ["质量管理"],
    }


def test_writer_and_qa_share_identical_project_prefix():
    bundle = _sample_bundle()
    writer_parts = build_writer_user_messages(bundle)
    qa_parts = build_qa_user_messages("正文片段", bundle)
    assert writer_parts[0] == qa_parts[0]
    assert writer_parts[0].startswith("## 全局工程信息")


def test_qa_user_messages_split_for_cache():
    parts = build_qa_user_messages("待检正文", _sample_bundle())
    assert len(parts) >= 3
    assert parts[0].startswith("## 全局工程信息")
    assert "当前章节" in parts[1]
    assert parts[-1].startswith("待质检正文片段")


def test_build_chunk_context_prefix_includes_folder_and_topic():
    prefix = build_chunk_context_prefix(
        folder="电力规范",
        source_file="电缆敷设.txt",
        keywords="弯曲半径",
        body="电缆最小弯曲半径不得小于15倍电缆外径。",
    )
    assert "电力规范" in prefix
    assert "电缆敷设" in prefix
    assert "弯曲半径" in prefix


def test_chunk_embed_and_display_include_prefix():
    body = "最小弯曲半径不得小于15倍外径。"
    prefix = "【所属：规范/电缆】"
    assert prefix in chunk_embed_text(body, prefix)
    assert prefix in chunk_display_text(body, prefix)


def test_build_cacheable_project_prefix_includes_facts():
    text = build_cacheable_project_prefix(_sample_bundle())
    assert "220kV" in text
    assert "180日历天" in text

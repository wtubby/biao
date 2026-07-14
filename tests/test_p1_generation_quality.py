"""P1：以标写标检索、规范惯例条目、长章分段。"""

import sys
from unittest.mock import MagicMock

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from services.generation_config import standards_pack_hint
from services.reference_bid_service import (
    build_reference_query,
    scrub_reference_identity,
    select_reference_bid_snippets,
)
from services.standards_pack import build_standards_hint, match_standards_clauses
from services.writer_service import _chunk_key_points, _should_segment_chapter
from prompts.writer_prompt import build_writer_user_prompt


def test_select_reference_bid_snippets_prefers_relevant_paragraph():
    ref = (
        "第一章 工程概况\n\n本工程位于四川，电压等级 220kV，总工期 180 天。\n\n"
        "第二章 质量管理\n\n建立三级质检体系，实行工序报验与旁站监督。\n\n"
        "第三章 施工进度计划\n\n采用三级网络计划控制关键节点，设置里程碑与周报制度，"
        "主变就位、受电调试等节点纳入关键路径管理。\n\n"
        "第四章 安全文明施工\n\n落实危险源辨识与应急预案，现场封闭管理。"
    )
    # 填充长度，触发检索而非全文返回
    ref = ref + ("\n\n补充说明段落，用于拉长参考文本。" * 40)
    query = build_reference_query(
        "施工进度计划",
        {"brief": "写网络计划与里程碑", "content_boundary": "只写进度"},
        ["进度控制"],
    )
    snippets = select_reference_bid_snippets(ref, query)
    assert "网络计划" in snippets or "里程碑" in snippets
    assert "危险源辨识" not in snippets or "网络计划" in snippets
    assert len(snippets) <= 1800


def test_select_reference_bid_short_text_returns_all():
    text = "短参考标书，直接全文注入。"
    assert select_reference_bid_snippets(text, "进度") == text


def test_scrub_reference_identity_removes_company_and_contact():
    raw = (
        "由某某电力工程有限公司负责实施。"
        "统一社会信用代码：91310000MA1K3XXXXX。"
        "项目经理：张三。"
        "合同编号：HT-2024-001。"
        "我公司承诺按期完工。"
    )
    cleaned = scrub_reference_identity(raw)
    assert "某某电力工程有限公司" not in cleaned
    assert "91310000MA1K3XXXXX" not in cleaned
    assert "张三" not in cleaned
    assert "HT-2024-001" not in cleaned
    assert "我公司" not in cleaned
    assert "投标人" in cleaned


def test_scrub_reference_identity_keeps_generic_power_company():
    """「电力公司」等通用行业指代不应被整体替换成「投标人」。"""
    raw = (
        "本工程建设完成后，将按规定移交属地电力公司统一调度运行，"
        "验收工作由建设单位与电力公司共同组织。"
    )
    cleaned = scrub_reference_identity(raw)
    assert "电力公司" in cleaned
    assert "属地投标人" not in cleaned
    assert "与投标人共同组织" not in cleaned


def test_select_reference_bid_snippets_scrubs_identity():
    ref = (
        "由某某建设集团有限公司编制施工进度计划，采用三级网络计划控制关键节点，"
        "设置里程碑与周报制度，主变就位纳入关键路径。"
    )
    snippets = select_reference_bid_snippets(ref, "进度 网络计划")
    assert "网络计划" in snippets
    assert "某某建设集团有限公司" not in snippets
    assert "投标人" in snippets


def test_standards_hint_matches_chapter_keywords():
    hint = build_standards_hint(
        "epc_guide",
        chapter_title="施工进度计划",
        brief="网络计划",
        boundary="只写进度",
    )
    assert "非完整标准条文库" in hint
    assert "进度类" in hint
    assert match_standards_clauses("none", chapter_title="进度") == []


def test_standards_pack_hint_wrapper():
    hint = standards_pack_hint("epc_guide", chapter_title="安全管理措施")
    assert "安全类" in hint
    assert standards_pack_hint("none") == ""


def test_chunk_key_points_groups():
    points = [f"要点{i}" for i in range(6)]
    groups = _chunk_key_points(points, max_groups=3)
    assert len(groups) == 3
    assert sum(len(g) for g in groups) == 6


def test_should_segment_chapter():
    bundle = {
        "guidance": {"target_words": 2000},
        "content_plan": {"key_points": ["a", "b", "c", "d"]},
    }
    assert _should_segment_chapter(bundle) is True
    bundle["_segment_mode"] = True
    assert _should_segment_chapter(bundle) is False
    assert _should_segment_chapter({
        "guidance": {"target_words": 800},
        "content_plan": {"key_points": ["a", "b", "c", "d"]},
    }) is False


def test_should_segment_chapter_allows_normal_sibling_leaves():
    """普通大纲同级多叶子不得禁用内存分段。"""
    from types import SimpleNamespace

    nodes = [
        SimpleNamespace(id="1.2.1", parent_id="1.2", is_leaf=1),
        SimpleNamespace(id="1.2.2", parent_id="1.2", is_leaf=1),
    ]
    bundle = {
        "guidance": {"target_words": 2000},
        "content_plan": {"key_points": ["a", "b", "c", "d"]},
        "chapter_id": "1.2.2",
        "chapter_parent_id": "1.2",
        "all_nodes": nodes,
    }
    assert _should_segment_chapter(bundle) is True


def test_should_segment_chapter_disabled_when_split_origin():
    """仅结构拆分产生的子叶子跳过内存分段。"""
    bundle = {
        "guidance": {"target_words": 2000, "split_origin": True},
        "content_plan": {"key_points": ["a", "b", "c", "d"]},
    }
    assert _should_segment_chapter(bundle) is False


def test_writer_prompt_empty_retrieval_and_segment_and_ref():
    prompt = build_writer_user_prompt({
        "global_params": {"工程名称": "测"},
        "project_overview": "",
        "requirements_text": "评分",
        "retrieval_text": "",
        "empty_retrieval_hint": "本节无可用检索素材：禁止编造规范标准号",
        "last_summary": "",
        "chapter_title": "施工方案",
        "chapter_level": 2,
        "chapter_path": "方案 > 施工方案",
        "guidance": {"brief": "写方案", "content_boundary": "只写本章", "target_words": 2000},
        "sibling_leaf_titles": [],
        "other_leaf_titles": ["质量措施"],
        "content_plan": {"key_points": ["吊装"], "technical_methods": [], "data_to_include": [],
                         "charts_needed": [], "word_count_target": 700, "avoid": []},
        "_segment_mode": True,
        "_segment_index": 1,
        "_segment_total": 2,
        "_segment_written": [],
        "_segment_remaining": ["调试"],
        "reference_bid_text": "参考：采用双机抬吊。",
        "standards_hint": "写作惯例（非完整标准条文库）",
        "chart_density_hint": "",
    })
    assert "检索说明" in prompt
    assert "禁止编造规范标准号" in prompt
    assert "分段撰写（第 1/2 段）" in prompt
    assert "后续段将写" in prompt
    assert "以标写标参考" in prompt
    assert "写作惯例提示" in prompt


def test_segmented_chapter_retries_empty_content(monkeypatch):
    from services.chapter_generation_service import _generate_segmented_chapter

    calls = {"n": 0}

    def fake_once(bundle, **kwargs):
        calls["n"] += 1
        seg_idx = bundle.get("_segment_index", 1)
        if seg_idx == 1 and calls["n"] == 1:
            return "", None
        return f"第{seg_idx}段施工内容说明。", None

    monkeypatch.setattr("services.chapter_generation_service._generate_once", fake_once)
    monkeypatch.setattr("services.chapter_generation_service.ENABLE_SEGMENT_QA", False)

    bundle = {
        "content_plan": {
            "key_points": ["要点一", "要点二", "要点三", "要点四"],
        },
        "guidance": {"target_words": 2000},
    }
    qa_context: dict = {"segment_warnings": []}
    content, _ = _generate_segmented_chapter(
        bundle,
        chat_messages=None,
        use_chat=False,
        total_max_tokens=4000,
        qa_context=qa_context,
    )
    assert calls["n"] >= 3
    assert "第1段" in content
    assert "第2段" in content
    assert not qa_context["segment_warnings"]


def test_segmented_chapter_warns_when_segment_stays_empty(monkeypatch):
    from services.chapter_generation_service import _generate_segmented_chapter

    def fake_once(bundle, **kwargs):
        seg_idx = bundle.get("_segment_index", 1)
        if seg_idx == 2:
            return "", None
        return f"第{seg_idx}段施工内容说明。", None

    monkeypatch.setattr("services.chapter_generation_service._generate_once", fake_once)
    monkeypatch.setattr("services.chapter_generation_service.ENABLE_SEGMENT_QA", False)
    monkeypatch.setattr("services.chapter_generation_service.MAX_SEGMENT_QA_RETRY", 1)

    bundle = {
        "content_plan": {
            "key_points": ["要点一", "要点二", "要点三", "要点四"],
        },
        "guidance": {"target_words": 2000},
    }
    qa_context: dict = {"segment_warnings": []}
    content, _ = _generate_segmented_chapter(
        bundle,
        chat_messages=None,
        use_chat=False,
        total_max_tokens=4000,
        qa_context=qa_context,
    )
    assert "第1段" in content
    assert "第2段" not in content
    assert any("第2/2段" in w for w in qa_context["segment_warnings"])

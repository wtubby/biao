"""P4：评分覆盖进重试、规划校验、事实一致性、跨章重叠、分段接缝。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from services.qa_rules import (
    check_atomic_markdown_closure,
    check_cross_chapter_overlap,
    check_global_fact_consistency,
    check_scoring_coverage_in_content,
    check_segment_stitch_quality,
    fallback_content_plan,
    validate_content_plan,
)
from prompts.plan_prompt import get_plan_system_prompt
from prompts.writer_prompt import build_writer_user_prompt
from prompts.qa_prompt import build_qa_user_prompt


def test_scoring_coverage_flags_missing_mandatory_and_keywords():
    req = SimpleNamespace(
        requirement_title="进度控制",
        keyword="网络计划,里程碑",
        mandatory_elements="三级网络计划|周报制度",
        is_risk_item=1,
    )
    content = "本章介绍进度管理总体思路，确保工期受控。"
    errors = check_scoring_coverage_in_content(content, [req])
    assert any("必备要素" in e for e in errors)

    content2 = (
        "采用三级网络计划与周报制度，设置里程碑节点，"
        "完全响应招标文件进度控制要求。"
    )
    assert check_scoring_coverage_in_content(content2, [req]) == []


def test_scoring_coverage_accepts_compliance_phrase_synonym():
    req = SimpleNamespace(
        requirement_title="总体实施方案",
        keyword="工程进度保障,工程质量保障",
        mandatory_elements="满足竞争性谈判文件要求",
        is_risk_item=0,
    )
    content = (
        "本方案完全符合竞争性谈判文件要求。\n"
        "## 进度保障\n"
        "编制网络计划并按里程碑考核。"
    )
    assert check_scoring_coverage_in_content(content, [req]) == []


def test_scoring_coverage_requires_substantial_for_risk():
    req = SimpleNamespace(
        requirement_title="质量管理",
        keyword="三级质检",
        mandatory_elements="",
        is_risk_item=1,
    )
    content = "现场实行三级质检，工序报验与旁站监督。"
    errors = check_scoring_coverage_in_content(content, [req])
    assert any("实质性响应" in e for e in errors)


def test_global_fact_consistency_count_conflict():
    facts = "主变台数：2台\n建设地点：成都市"
    content = "本工程主变台数为3台，布置于GIS室。"
    errors = check_global_fact_consistency(
        content,
        facts_text=facts,
        global_params={"建设地点": "成都市", "电压等级": "220kV"},
    )
    assert any("主变台数" in e for e in errors)


def test_global_fact_consistency_ignores_reference_city():
    """引用其他省市同类工程经验不应报建设地点不一致。"""
    content = (
        "本工程施工组织参考了类似电压等级、类似规模的上海市某变电站工程经验，"
        "结合本工程实际编制专项方案。"
    )
    errors = check_global_fact_consistency(
        content,
        global_params={"建设地点": "四川省成都市"},
    )
    assert not any("建设地点" in e for e in errors)


def test_global_fact_consistency_flags_explicit_location_claim():
    """明确声明建设地点与全局不符时应检出，且片段为干净地名。"""
    content = "本工程建设地点为上海市浦东新区，电压等级220kV。"
    errors = check_global_fact_consistency(
        content,
        global_params={"建设地点": "四川省成都市"},
    )
    assert any("建设地点疑似不一致" in e for e in errors)
    assert any("上海市" in e for e in errors)
    assert not any("类似规模" in e for e in errors)


def test_global_fact_consistency_allows_matching_city_claim():
    content = "本工程建设地点为成都市高新区，总工期180天。"
    errors = check_global_fact_consistency(
        content,
        global_params={"建设地点": "四川省成都市"},
    )
    assert not any("建设地点" in e for e in errors)


def test_cross_chapter_overlap_detects_reuse():
    prior = (
        "采用双机抬吊完成主变就位，吊装前复核基础轴线与标高，"
        "设置警戒区并安排专人指挥，全过程旁站监督。"
    ) * 3
    content = prior + "本章补充调试方案与受电条件确认。"
    errors = check_cross_chapter_overlap(content, [prior])
    assert errors and "重复" in errors[0]


def test_segment_stitch_quality_flags_opener_and_overlap():
    p1 = "首段写吊装工艺与参数控制，设置警戒区并安排专人指挥。" * 3
    p2 = "综上所述，继续上文吊装工艺与参数控制，设置警戒区并安排专人指挥。" + ("补充调试。" * 5)
    errors = check_segment_stitch_quality([p1, p2])
    assert errors
    assert all(isinstance(e, dict) and "index" in e and "message" in e for e in errors)
    assert all(e["index"] == 1 for e in errors)
    assert any("套话" in e["message"] or "接缝" in e["message"] for e in errors)


def test_segment_stitch_quality_indexes_middle_segment():
    """中间段接缝问题应标到该段下标，而不是末段。"""
    p1 = "首段写吊装工艺与参数控制，设置警戒区并安排专人指挥。" * 3
    p2 = "综上所述，继续上文吊装工艺与参数控制，设置警戒区并安排专人指挥。" + ("补充调试。" * 5)
    p3 = "末段写受电条件确认与试运行安排，明确责任分工。" * 3
    errors = check_segment_stitch_quality([p1, p2, p3])
    assert errors
    assert all(e["index"] == 1 for e in errors)
    assert not any(e["index"] == 2 for e in errors)


def test_segment_stitch_quality_detects_phase_shifted_sentence_dup():
    """整句重复但起始偏移不同时，滑动 n-gram 仍应检出（旧贪婪切块会漏检）。"""
    dup = "本工程严格按照国家现行施工验收规范执行质量控制流程确保工程质量和进度符合合同要求"
    p1 = "前文垫字若干。" + dup + "。后文继续讲吊装工艺与参数控制设置警戒区。"
    p2 = "别的前缀。" + dup + "。然后本段继续讲调试方案与受电条件确认责任分工。"
    errors = check_segment_stitch_quality([p1, p2])
    assert any(e["index"] == 1 and "接缝" in e["message"] for e in errors)


def test_segment_stitch_quality_ignores_unrelated_segments():
    p1 = "首段写吊装工艺与参数控制，设置警戒区并安排专人指挥。" * 4
    p2 = "末段写受电条件确认与试运行安排，明确责任分工与验收标准。" * 4
    errors = check_segment_stitch_quality([p1, p2])
    assert not any("接缝" in e["message"] for e in errors)


def test_atomic_markdown_closure_flags_incomplete_table_and_chart():
    table_only = "| 列A | 列B |\n| --- | --- |"
    errs = check_atomic_markdown_closure(table_only)
    assert any("数据行" in e for e in errs)

    truncated_row = "正文段落。\n| 列A | 列B |"
    errs2 = check_atomic_markdown_closure(truncated_row)
    assert any("表格" in e for e in errs2)

    open_chart = "流程如下：[FLOW_DATA: {\"steps\": [\"a\""
    errs3 = check_atomic_markdown_closure(open_chart)
    assert any("占位符" in e for e in errs3)

    complete = "| 列A | 列B |\n| --- | --- |\n| 1 | 2 |\n\n段落结束。"
    assert check_atomic_markdown_closure(complete) == []


def test_validate_and_fallback_content_plan():
    bundle = {
        "chapter_title": "施工方案",
        "guidance": {"target_words": 2000, "brief": "写吊装"},
        "last_summary": "上章已写进度计划",
        "requirements_text": "【进度控制】\n【质量管理】",
    }
    assert validate_content_plan({}, bundle)
    assert validate_content_plan({"key_points": ["仅一条"]}, bundle)
    good = {
        "key_points": ["吊装", "就位", "验收"],
        "technical_methods": ["双机抬吊"],
        "avoid": ["勿重复进度计划"],
        "word_count_target": 2000,
    }
    assert validate_content_plan(good, bundle) == []
    fb = fallback_content_plan(bundle)
    assert len(fb["key_points"]) >= 2
    assert fb.get("_fallback") is True


def test_validate_content_plan_flags_missing_mandatory_elements():
    """key_points 未覆盖必备要素时应报错（复现原参数反序 bug 的场景）。"""
    req = SimpleNamespace(
        requirement_title="进度控制",
        mandatory_elements="三级网络计划|周报制度",
    )
    bundle = {
        "chapter_title": "施工方案",
        "guidance": {"target_words": 2000, "brief": "写进度"},
        "requirements_text": "【进度控制】",
        "requirements": [req],
    }
    plan = {
        "key_points": ["总体进度安排", "关键节点控制"],
        "technical_methods": ["流水施工"],
    }
    issues = validate_content_plan(plan, bundle)
    assert any("必备要素" in i for i in issues)


def test_validate_content_plan_passes_when_mandatory_elements_covered():
    """key_points 已实际覆盖必备要素时不应误报（回归防护）。"""
    req = SimpleNamespace(
        requirement_title="进度控制",
        mandatory_elements="三级网络计划|周报制度",
    )
    bundle = {
        "chapter_title": "施工方案",
        "guidance": {"target_words": 2000, "brief": "写进度"},
        "requirements_text": "【进度控制】",
        "requirements": [req],
    }
    plan = {
        "key_points": ["建立三级网络计划体系", "执行周报制度跟踪进度"],
        "technical_methods": ["流水施工"],
    }
    issues = validate_content_plan(plan, bundle)
    assert not any("必备要素" in i for i in issues)


def test_plan_system_prompt_domain_aware():
    assert "市政工程" in get_plan_system_prompt("市政工程")
    assert "电力工程" in get_plan_system_prompt("电力工程")


def test_writer_and_qa_prompts_include_prior_and_plan():
    bundle = {
        "global_params": {"工程名称": "测"},
        "project_overview": "",
        "requirements_text": "评分",
        "retrieval_text": "",
        "last_summary": "上章摘要",
        "chapter_title": "施工方案",
        "chapter_level": 2,
        "chapter_path": "a > b",
        "guidance": {"brief": "写方案", "content_boundary": "只写本章"},
        "sibling_leaf_titles": [],
        "other_leaf_titles": [],
        "prior_summaries": ["「进度」已写网络计划"],
        "contradictions": [{"summary": "工期条款前后不一致"}],
        "content_plan": {
            "key_points": ["吊装", "就位"],
            "avoid": ["勿重复进度"],
        },
        "global_facts_text": "主变：2台",
    }
    writer = build_writer_user_prompt(bundle)
    assert "前序章节已写要点" in writer
    assert "招标文件已知矛盾" in writer
    qa = build_qa_user_prompt("正文内容足够长用于质检。" * 20, bundle)
    assert "本章写作规划预期覆盖要点" in qa
    assert "前序章节摘要" in qa

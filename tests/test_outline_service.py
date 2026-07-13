"""大纲两阶段生成单元测试。"""

import json
from unittest.mock import patch

from prompts.outline_prompt import build_branch_user_prompt
from services.outline_service import (
    _ensure_unique_outline_ids,
    _fallback_branch_leaf,
    _guess_bound_folder,
    _match_requirements_for_title,
    _sanitize_branch_expand_nodes,
    enrich_outline_nodes,
    generate_outline_skeleton,
    _expand_branch,
)


_GLOBAL_INFO = {
    "工程名称": "测试变电站工程",
    "项目类型": "变电站新建",
    "电压等级": "220kV",
    "工程规模": "2×180MVA",
    "总工期": 180,
    "建设地点": "某市",
    "工程领域": "电力工程",
}

_CATALOG = [
    {"title": "工程概况", "level": 1, "sort_order": 1},
    {"title": "施工组织设计", "level": 1, "sort_order": 2},
]


def test_generate_outline_skeleton_returns_level1_and_level2():
    fake_result = {
        "nodes": [
            {"id": "1", "title": "工程概况", "parent_id": None, "level": 1, "is_leaf": 0, "sort_order": 1},
            {"id": "2", "title": "施工组织设计", "parent_id": None, "level": 1, "is_leaf": 0, "sort_order": 2},
            {"id": "2.1", "title": "土建工程", "parent_id": "2", "level": 2, "is_leaf": 0, "sort_order": 1},
            {"id": "2.2", "title": "电气安装工程", "parent_id": "2", "level": 2, "is_leaf": 0, "sort_order": 2},
        ]
    }
    with patch("services.outline_service.call_llm_json", return_value=fake_result):
        nodes = generate_outline_skeleton(_GLOBAL_INFO, _CATALOG, "参考结构文本")
    level1 = [n for n in nodes if n["level"] == 1]
    level2 = [n for n in nodes if n["level"] == 2]
    assert len(level1) == 2
    assert len(level2) == 2


def test_generate_outline_skeleton_raises_without_level1():
    with patch("services.outline_service.call_llm_json", return_value={"nodes": []}):
        try:
            generate_outline_skeleton(_GLOBAL_INFO, _CATALOG, "参考结构文本")
            assert False, "应抛出 ValueError"
        except ValueError:
            pass


def test_build_branch_user_prompt_includes_other_branches():
    branch = {"id": "2.1", "title": "土建工程", "parent_id": "2", "level": 2}
    others = [
        {"id": "2.2", "title": "电气安装工程", "parent_id": "2"},
        {"id": "2.3", "title": "调试试验", "parent_id": "2"},
    ]
    prompt = build_branch_user_prompt(
        _GLOBAL_INFO, branch, _CATALOG, [], [], other_branches=others,
    )
    assert "<other_branches>" in prompt
    assert "电气安装工程" in prompt
    assert "调试试验" in prompt
    other_block = prompt.split("<other_branches>")[1].split("</other_branches>")[0]
    assert "土建工程" not in other_block


def test_expand_branch_no_split_returns_branch_itself():
    branch = {"id": "1.1", "title": "项目目标", "parent_id": "1", "level": 2}
    fake_result = {
        "nodes": [
            {
                "id": "1.1", "title": "项目目标", "parent_id": "1", "level": 2, "is_leaf": 1,
                "requirement_ids": ["req-1"], "writing_guidance": "写质量工期造价目标",
                "content_boundary": "写质量、工期、造价目标承诺，不写保证措施。",
            }
        ]
    }
    with patch("services.outline_service.call_llm_json", return_value=fake_result):
        nodes = _expand_branch(_GLOBAL_INFO, branch, _CATALOG, [], [])
    assert len(nodes) == 1
    assert nodes[0]["id"] == "1.1"
    assert nodes[0]["is_leaf"] == 1


def test_expand_branch_split_returns_children():
    branch = {"id": "2.1", "title": "土建工程", "parent_id": "2", "level": 2}
    fake_result = {
        "nodes": [
            {"id": "2.1.1", "title": "基础工程", "parent_id": "2.1", "level": 3, "is_leaf": 1,
             "requirement_ids": [], "writing_guidance": "写基础施工工艺", "content_boundary": "写基础施工工艺与质量控制。"},
            {"id": "2.1.2", "title": "构支架安装", "parent_id": "2.1", "level": 3, "is_leaf": 1,
             "requirement_ids": [], "writing_guidance": "写构支架安装要点", "content_boundary": "写构支架安装工艺与允许偏差。"},
        ]
    }
    with patch("services.outline_service.call_llm_json", return_value=fake_result):
        nodes = _expand_branch(_GLOBAL_INFO, branch, _CATALOG, [], [])
    assert len(nodes) == 2
    assert all(n["id"] != "2.1" for n in nodes)


def test_fallback_branch_leaf_includes_guidance_and_guess_binding():
    reqs = [
        {"id": "r1", "title": "施工组织设计", "score_value": 10, "is_risk_item": 0, "score_category": "施工方案"},
    ]
    branch = {"id": "2.1", "title": "施工组织设计", "parent_id": "2", "level": 2}
    node = _fallback_branch_leaf(branch, reqs, ["主变安装", "GIS安装"])
    assert node["is_leaf"] == 1
    assert "r1" in node["requirement_ids"]
    assert node.get("writing_guidance")
    assert node.get("content_boundary")


def test_guess_bound_folder_returns_none_when_no_match():
    """无匹配时不得回落到 knowledge_folders[0]，避免错误检索。"""
    folders = ["主变安装", "GIS安装", "电缆敷设"]
    assert _guess_bound_folder("项目管理机构及人员配置", folders) is None
    assert _guess_bound_folder("主变安装方案", folders) == "主变安装"


def test_match_requirements_for_title_by_category():
    reqs = [{"id": "r2", "title": "Foo", "score_category": "质量管理"}]
    assert _match_requirements_for_title("质量保证措施", reqs) == []
    assert "r2" in _match_requirements_for_title("质量管理", reqs)


def test_enrich_outline_nodes_accepts_guidance_brief():
    nodes = enrich_outline_nodes(
        [{
            "id": "1",
            "title": "施工方案",
            "is_leaf": 1,
            "requirement_ids": [],
            "guidance_brief": "写施工工艺",
            "content_boundary": "只写工艺，不写组织",
        }],
        [],
    )
    wg = json.loads(nodes[0]["writing_guidance"])
    assert wg["brief"] == "写施工工艺"
    assert wg["content_boundary"] == "只写工艺，不写组织"


def test_enrich_outline_nodes_unscored_leaves_use_remaining_budget():
    """未绑定评分项的叶子应从剩余预算均分，不得再拿全量 target_pages 重切。"""
    from config import WORDS_PER_SCORE_PAGE
    from services.writing_guidance import parse_writing_guidance

    target_pages = 40
    total_budget = target_pages * WORDS_PER_SCORE_PAGE
    # 评分项总分 100，但只绑定 80 分，留出 20% 预算给未绑定叶子
    requirements = [
        {"id": "r1", "title": "施工组织", "score_value": 50, "is_risk_item": 0},
        {"id": "r2", "title": "质量保证", "score_value": 30, "is_risk_item": 0},
        {"id": "r3", "title": "未绑定项", "score_value": 20, "is_risk_item": 0},
    ]
    nodes = [
        {"id": "1", "title": "施工组织", "is_leaf": 1, "requirement_ids": ["r1"],
         "guidance_brief": "写组织", "content_boundary": "写施工组织"},
        {"id": "2", "title": "质量保证", "is_leaf": 1, "requirement_ids": ["r2"],
         "guidance_brief": "写质量", "content_boundary": "写质量保证"},
        {"id": "3", "title": "项目管理", "is_leaf": 1, "requirement_ids": [],
         "guidance_brief": "写管理", "content_boundary": "写项目管理"},
        {"id": "4", "title": "售后服务", "is_leaf": 1, "requirement_ids": [],
         "guidance_brief": "写售后", "content_boundary": "写售后服务"},
    ]
    enriched = enrich_outline_nodes(nodes, requirements, target_pages=target_pages)
    words = [
        parse_writing_guidance(n["writing_guidance"])["target_words"] or 0
        for n in enriched
    ]
    scored_total = words[0] + words[1]
    unscored_each = words[2]
    assert words[2] == words[3]
    expected_scored = int(round(50 * (target_pages / 100) * WORDS_PER_SCORE_PAGE)) + int(
        round(30 * (target_pages / 100) * WORDS_PER_SCORE_PAGE)
    )
    remaining = max(0, total_budget - expected_scored)
    expected_unscored = max(400, int(round(remaining / 2)))
    assert scored_total == expected_scored
    assert unscored_each == expected_unscored
    assert sum(words) == expected_scored + 2 * expected_unscored
    # 回归：旧逻辑会给未绑定叶子 target_pages*WPS/leaf_count，导致总和远超预算
    old_unscored = max(400, int(round(total_budget / 4)))
    assert unscored_each < old_unscored
    assert sum(words) <= total_budget + 2  # 允许四舍五入误差


def test_enrich_outline_nodes_unscored_zero_when_budget_exhausted():
    """评分叶子已分完全部预算时，未绑定叶子不再强制保底 400，避免超页。"""
    from config import WORDS_PER_SCORE_PAGE
    from services.writing_guidance import parse_writing_guidance

    target_pages = 40
    total_budget = target_pages * WORDS_PER_SCORE_PAGE
    requirements = [
        {"id": "r1", "title": "施工组织", "score_value": 70, "is_risk_item": 0},
        {"id": "r2", "title": "质量保证", "score_value": 30, "is_risk_item": 0},
    ]
    nodes = [
        {"id": "1", "title": "施工组织", "is_leaf": 1, "requirement_ids": ["r1"],
         "guidance_brief": "写组织", "content_boundary": "写施工组织"},
        {"id": "2", "title": "质量保证", "is_leaf": 1, "requirement_ids": ["r2"],
         "guidance_brief": "写质量", "content_boundary": "写质量保证"},
        {"id": "3", "title": "项目管理", "is_leaf": 1, "requirement_ids": [],
         "guidance_brief": "写管理", "content_boundary": "写项目管理"},
        {"id": "4", "title": "售后服务", "is_leaf": 1, "requirement_ids": [],
         "guidance_brief": "写售后", "content_boundary": "写售后服务"},
    ]
    enriched = enrich_outline_nodes(nodes, requirements, target_pages=target_pages)
    words = [
        parse_writing_guidance(n["writing_guidance"])["target_words"] or 0
        for n in enriched
    ]
    assert words[2] == 0
    assert words[3] == 0
    assert sum(words) <= total_budget + 2


def test_enrich_outline_nodes_shared_requirement_not_double_counted():
    """同一评分项绑定多个叶子时，字数预算应均分，总和不超过目标页预算。"""
    from config import WORDS_PER_SCORE_PAGE
    from services.writing_guidance import parse_writing_guidance

    target_pages = 40
    total_budget = target_pages * WORDS_PER_SCORE_PAGE
    requirements = [
        {"id": "r1", "title": "施工组织", "score_value": 100, "is_risk_item": 0},
    ]
    nodes = [
        {"id": "1", "title": "组织机构", "is_leaf": 1, "requirement_ids": ["r1"],
         "guidance_brief": "写机构", "content_boundary": "写组织机构"},
        {"id": "2", "title": "人员配置", "is_leaf": 1, "requirement_ids": ["r1"],
         "guidance_brief": "写人员", "content_boundary": "写人员配置"},
        {"id": "3", "title": "机具配置", "is_leaf": 1, "requirement_ids": ["r1"],
         "guidance_brief": "写机具", "content_boundary": "写机具配置"},
    ]
    enriched = enrich_outline_nodes(nodes, requirements, target_pages=target_pages)
    words = [
        parse_writing_guidance(n["writing_guidance"])["target_words"] or 0
        for n in enriched if n.get("is_leaf")
    ]
    assert len(words) == 3
    assert words[0] == words[1] == words[2]
    assert sum(words) <= total_budget + 3
    # 旧逻辑会对每个叶子各给 100% 预算，总和约 3 倍
    assert sum(words) < total_budget * 1.5


def test_sanitize_branch_expand_nodes_renames_wrong_prefix_ids():
    branch = {"id": "2.1", "title": "土建工程", "parent_id": "2", "level": 2}
    nodes = [
        {"id": "1.1", "title": "基础", "parent_id": "1", "level": 3, "is_leaf": 1},
        {"id": "1.2", "title": "构支架", "parent_id": "1", "level": 3, "is_leaf": 1},
    ]
    fixed, warnings = _sanitize_branch_expand_nodes(branch, nodes, used_ids={"1", "2"})
    assert [n["id"] for n in fixed] == ["2.1.1", "2.1.2"]
    assert all(n["parent_id"] == "2.1" for n in fixed)
    assert warnings


def test_sanitize_branch_expand_nodes_avoids_cross_branch_id_collision():
    branch_a = {"id": "2.1", "title": "土建", "parent_id": "2", "level": 2}
    branch_b = {"id": "2.2", "title": "电气", "parent_id": "2", "level": 2}
    occupied = {"1", "2"}
    nodes_a, _ = _sanitize_branch_expand_nodes(
        branch_a,
        [{"id": "1.1", "title": "A", "parent_id": "1", "level": 3, "is_leaf": 1}],
        used_ids=occupied,
    )
    nodes_b, _ = _sanitize_branch_expand_nodes(
        branch_b,
        [{"id": "1.1", "title": "B", "parent_id": "1", "level": 3, "is_leaf": 1}],
        used_ids=occupied,
    )
    all_ids = [nodes_a[0]["id"], nodes_b[0]["id"]]
    assert len(set(all_ids)) == 2
    assert all_ids == ["2.1.1", "2.2.1"]


def test_ensure_unique_outline_ids_renames_global_duplicates():
    nodes = [
        {"id": "1", "title": "概述", "parent_id": None, "level": 1},
        {"id": "1", "title": "重复", "parent_id": "1", "level": 2},
    ]
    fixed, warnings = _ensure_unique_outline_ids(nodes)
    assert fixed[0]["id"] == "1"
    assert fixed[1]["id"] != "1"
    assert warnings

"""Phase 2：规划期长章节结构化拆分。"""

from prompts.outline_split_prompt import get_split_system_prompt
from services.outline_split_service import (
    _assign_requirement_ids,
    apply_leaf_split,
    find_long_leaves,
    is_splittable_leaf,
    leaf_target_words,
    validate_split_nodes,
)


def test_get_split_system_prompt_no_double_period():
    text = get_split_system_prompt("电力")
    assert "。。你会收到" not in text
    assert "技术方案大纲策划专家" in text
    assert "你会收到" in text


def test_is_splittable_leaf_by_words():
    node = {
        "id": "1.2",
        "title": "施工部署",
        "is_leaf": 1,
        "level": 2,
        "target_words": 2800,
    }
    ok, _ = is_splittable_leaf(node, threshold=1500)
    assert ok is True

    short = {**node, "target_words": 800}
    ok2, reason = is_splittable_leaf(short, threshold=1500)
    assert ok2 is False
    assert "低于阈值" in reason


def test_is_splittable_leaf_skips_descriptive():
    node = {
        "id": "1.1",
        "title": "工程概况",
        "is_leaf": 1,
        "level": 2,
        "target_words": 2000,
    }
    ok, reason = is_splittable_leaf(node, threshold=1500)
    assert ok is False
    assert "概况" in reason


def test_validate_split_nodes_requires_three_children():
    raw = [
        {"id_suffix": "1", "title": "流水段划分", "guidance_brief": "写划分原则"},
        {"id_suffix": "2", "title": "劳动力配置", "guidance_brief": "写班组配置"},
    ]
    cleaned, issues = validate_split_nodes(raw)
    assert len(cleaned) < 3
    assert issues


def test_validate_split_nodes_filters_illegal_requirement_ids():
    raw = [
        {
            "id_suffix": "1",
            "title": "流水段划分",
            "guidance_brief": "写划分",
            "content_boundary": "只写划分",
            "requirement_ids": ["req-1", "forged"],
        },
        {
            "id_suffix": "2",
            "title": "劳动力配置",
            "guidance_brief": "写班组",
            "content_boundary": "只写人力",
            "requirement_ids": ["req-2"],
        },
        {
            "id_suffix": "3",
            "title": "机械时序",
            "guidance_brief": "写机械",
            "content_boundary": "只写机械",
            "requirement_ids": [],
        },
    ]
    cleaned, issues = validate_split_nodes(raw, allowed_req_ids={"req-1", "req-2"})
    assert not issues
    assert cleaned[0]["requirement_ids"] == ["req-1"]
    assert cleaned[1]["requirement_ids"] == ["req-2"]
    assert cleaned[2]["requirement_ids"] == []


def test_validate_split_nodes_renumbers_duplicate_id_suffix():
    """LLM 返回重复 id_suffix 时按顺序重编号，不丢子节点。"""
    raw = [
        {
            "id_suffix": "1",
            "title": "A",
            "guidance_brief": "写A",
            "content_boundary": "只写A",
        },
        {
            "id_suffix": "2",
            "title": "B",
            "guidance_brief": "写B",
            "content_boundary": "只写B",
        },
        {
            "id_suffix": "2",
            "title": "C",
            "guidance_brief": "写C",
            "content_boundary": "只写C",
        },
    ]
    cleaned, issues = validate_split_nodes(raw)
    assert not issues
    assert [c["id_suffix"] for c in cleaned] == ["1", "2", "3"]
    assert [c["title"] for c in cleaned] == ["A", "B", "C"]


def test_apply_leaf_split_unique_ids_despite_duplicate_suffix():
    nodes = [
        {"id": "3", "title": "Root", "parent_id": None, "level": 1, "is_leaf": 0, "sort_order": 1},
        {
            "id": "3.2",
            "title": "X",
            "parent_id": "3",
            "level": 2,
            "is_leaf": 1,
            "sort_order": 2,
            "requirement_ids": [],
            "target_words": 3000,
            "guidance_brief": "写X",
            "content_boundary": "写X",
        },
    ]
    specs = [
        {
            "id_suffix": "1",
            "title": "A",
            "guidance_brief": "写A",
            "content_boundary": "只写A",
            "requirement_ids": [],
        },
        {
            "id_suffix": "2",
            "title": "B",
            "guidance_brief": "写B",
            "content_boundary": "只写B",
            "requirement_ids": [],
        },
        {
            "id_suffix": "2",
            "title": "C",
            "guidance_brief": "写C",
            "content_boundary": "只写C",
            "requirement_ids": [],
        },
    ]
    updated = apply_leaf_split(nodes, "3.2", specs)
    children = sorted(
        [n for n in updated if n.get("parent_id") == "3.2"],
        key=lambda n: n["id"],
    )
    assert [c["id"] for c in children] == ["3.2.1", "3.2.2", "3.2.3"]
    assert [c["title"] for c in children] == ["A", "B", "C"]
    assert len({c["id"] for c in children}) == 3
    assert len([n for n in updated if n.get("id") == "3.2.2"]) == 1


def test_apply_leaf_split_restructures_tree():
    nodes = [
        {"id": "1", "title": "施工组织", "parent_id": None, "level": 1, "is_leaf": 0, "sort_order": 1},
        {
            "id": "1.2",
            "title": "施工部署",
            "parent_id": "1",
            "level": 2,
            "is_leaf": 1,
            "sort_order": 2,
            "requirement_ids": ["req-1", "req-2"],
            "bound_folder": "主变安装",
            "target_words": 3000,
            "guidance_brief": "写部署",
            "content_boundary": "写施工部署",
        },
    ]
    specs = [
        {
            "id_suffix": "1",
            "title": "流水段划分",
            "guidance_brief": "写A/B区",
            "content_boundary": "只写划分",
            "requirement_ids": ["req-1"],
        },
        {
            "id_suffix": "2",
            "title": "劳动力配置",
            "guidance_brief": "写班组",
            "content_boundary": "只写人力",
            "requirement_ids": ["req-2"],
        },
        {
            "id_suffix": "3",
            "title": "机械时序",
            "guidance_brief": "写机械",
            "content_boundary": "只写机械",
            "requirement_ids": [],
        },
    ]
    updated = apply_leaf_split(nodes, "1.2", specs)
    parent = next(n for n in updated if n["id"] == "1.2")
    children = sorted(
        [n for n in updated if n.get("parent_id") == "1.2"],
        key=lambda n: n["id"],
    )
    assert parent["is_leaf"] == 0
    assert parent.get("requirement_ids") == []
    assert len(children) == 3
    assert all(c["is_leaf"] == 1 for c in children)
    assert children[0]["requirement_ids"] == ["req-1"]
    assert children[1]["requirement_ids"] == ["req-2"]
    assert children[2]["requirement_ids"] == []
    assert leaf_target_words(children[0]) == 1000
    from services.writing_guidance import parse_writing_guidance

    assert all(parse_writing_guidance(c["writing_guidance"])["split_origin"] for c in children)


def test_assign_requirement_ids_fallback_uncovered():
    """LLM 未分配时，未覆盖 req 挂到最相关子节点，不全员继承。"""
    specs = [
        {
            "id_suffix": "1",
            "title": "流水段划分",
            "guidance_brief": "写区段划分",
            "content_boundary": "只写划分",
            "requirement_ids": [],
        },
        {
            "id_suffix": "2",
            "title": "劳动力配置",
            "guidance_brief": "写班组配置",
            "content_boundary": "只写人力",
            "requirement_ids": [],
        },
        {
            "id_suffix": "3",
            "title": "机械时序",
            "guidance_brief": "写机械进场",
            "content_boundary": "只写机械",
            "requirement_ids": [],
        },
    ]
    reqs = [
        {
            "id": "req-labor",
            "title": "劳动力组织",
            "keyword": "班组",
            "mandatory_elements": "劳动力配置",
        },
    ]
    assigned = _assign_requirement_ids(specs, ["req-labor"], reqs)
    bound = [s for s in assigned if "req-labor" in s["requirement_ids"]]
    assert len(bound) == 1
    assert bound[0]["title"] == "劳动力配置"
    assert sum(1 for s in assigned if s["requirement_ids"] == ["req-labor"]) == 1


def test_assign_requirement_ids_fallback_to_first_when_no_match():
    specs = [
        {
            "id_suffix": "1",
            "title": "甲主题",
            "guidance_brief": "写甲",
            "content_boundary": "只写甲",
            "requirement_ids": [],
        },
        {
            "id_suffix": "2",
            "title": "乙主题",
            "guidance_brief": "写乙",
            "content_boundary": "只写乙",
            "requirement_ids": [],
        },
        {
            "id_suffix": "3",
            "title": "丙主题",
            "guidance_brief": "写丙",
            "content_boundary": "只写丙",
            "requirement_ids": [],
        },
    ]
    assigned = _assign_requirement_ids(
        specs,
        ["orphan-req"],
        [{"id": "orphan-req", "title": "无关评分", "keyword": "", "mandatory_elements": ""}],
    )
    assert assigned[0]["requirement_ids"] == ["orphan-req"]
    assert assigned[1]["requirement_ids"] == []
    assert assigned[2]["requirement_ids"] == []


def test_apply_leaf_split_does_not_broadcast_all_reqs():
    nodes = [
        {
            "id": "1.2",
            "title": "施工部署",
            "parent_id": None,
            "level": 2,
            "is_leaf": 1,
            "sort_order": 1,
            "requirement_ids": ["req-1", "req-2"],
            "target_words": 3000,
            "guidance_brief": "写部署",
            "content_boundary": "写施工部署",
        },
    ]
    specs = [
        {
            "id_suffix": "1",
            "title": "流水段",
            "guidance_brief": "写划分",
            "content_boundary": "划分",
            "requirement_ids": [],
        },
        {
            "id_suffix": "2",
            "title": "劳动力",
            "guidance_brief": "写人力",
            "content_boundary": "人力",
            "requirement_ids": [],
        },
        {
            "id_suffix": "3",
            "title": "机械",
            "guidance_brief": "写机械",
            "content_boundary": "机械",
            "requirement_ids": [],
        },
    ]
    updated = apply_leaf_split(nodes, "1.2", specs)
    children = [n for n in updated if n.get("parent_id") == "1.2"]
    all_ids = [rid for c in children for rid in c["requirement_ids"]]
    assert set(all_ids) == {"req-1", "req-2"}
    assert not all(c["requirement_ids"] == ["req-1", "req-2"] for c in children)


def test_find_long_leaves():
    nodes = [
        {"id": "a", "title": "短章", "is_leaf": 1, "level": 2, "target_words": 600},
        {"id": "b", "title": "长章", "is_leaf": 1, "level": 2, "target_words": 2200},
    ]
    found = find_long_leaves(nodes, threshold=1500)
    assert len(found) == 1
    assert found[0]["id"] == "b"

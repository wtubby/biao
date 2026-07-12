"""content_boundary 质量门禁测试。"""

import json

from services.outline_boundary_rules import (
    sanitize_leaf_content_boundaries,
    validate_content_boundary,
)
from services.outline_service import enrich_outline_nodes


def test_validate_goal_boundary_rejects_measures():
    issues = validate_content_boundary(
        "项目质量目标",
        "写质量目标，并说明质量保证措施与检验频次。",
    )
    assert any("禁止词" in i for i in issues)


def test_validate_overview_boundary_rejects_scheme():
    issues = validate_content_boundary(
        "工程概况",
        "写工程概况，并说明施工组织与专项方案安排。",
    )
    assert any("禁止词" in i for i in issues)


def test_sanitize_replaces_invalid_goal_boundary():
    nodes = [
        {
            "id": "1.1",
            "title": "项目质量目标",
            "is_leaf": 1,
            "content_boundary": "写目标并附质量保证措施。",
            "guidance_brief": "写目标",
        }
    ]
    fixed, warnings = sanitize_leaf_content_boundaries(nodes)
    assert warnings
    wg = json.loads(fixed[0]["writing_guidance"])
    assert "措施" not in wg["content_boundary"] or "不写" in wg["content_boundary"]


def test_enrich_outline_nodes_applies_boundary_gate():
    nodes = [
        {
            "id": "1.1",
            "title": "工程概况",
            "is_leaf": 1,
            "content_boundary": "写概况与施工组织方案。",
            "guidance_brief": "写概况",
        }
    ]
    enriched = enrich_outline_nodes(nodes, [], target_pages=50)
    wg = json.loads(enriched[0]["writing_guidance"])
    assert "施工组织" not in wg["content_boundary"]

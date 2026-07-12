"""generate_outline_ai 集成测试（mock LLM）。"""

import json
from unittest.mock import MagicMock, patch

from services.outline_service import generate_outline_ai


def test_generate_outline_ai_saves_outline():
    project = MagicMock()
    project.id = "p1"
    project.name = "测试工程"
    project.voltage_level = "220kV"
    project.capacity = "2×180MVA"
    project.duration_days = 180
    project.location = "某市"
    project.extra_params = json.dumps({
        "project_type": "变电站新建",
        "outline_catalog": [
            {"title": "工程概况", "level": 1},
            {"title": "施工组织设计", "level": 1},
        ],
        "outline_catalog_text": "工程概况\n施工组织设计",
    })

    req = MagicMock()
    req.id = "r1"
    req.requirement_title = "施工组织设计"
    req.score_value = 10
    req.is_risk_item = 0
    req.score_category = "施工方案"
    req.status = "confirmed"

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [req],
        [],
    ]

    skeleton = {
        "nodes": [
            {"id": "1", "title": "工程概况", "level": 1, "is_leaf": 0, "sort_order": 1},
            {"id": "2", "title": "施工组织设计", "level": 1, "is_leaf": 0, "sort_order": 2},
            {"id": "2.1", "title": "施工组织设计", "parent_id": "2", "level": 2, "is_leaf": 0, "sort_order": 1},
        ]
    }
    branch = {
        "nodes": [{
            "id": "2.1", "title": "施工组织设计", "parent_id": "2", "level": 2, "is_leaf": 1,
            "requirement_ids": ["r1"], "writing_guidance": "写施工组织", "content_boundary": "写施工组织要点。",
        }]
    }

    with patch("services.outline_service.call_llm_json", side_effect=[skeleton, branch]):
        outlines, source, warnings = generate_outline_ai(db, project)

    assert source == "user_catalog"
    assert len(outlines) >= 1
    assert db.commit.called


def test_generate_outline_ai_records_node_warning_on_branch_failure():
    project = MagicMock()
    project.id = "p1"
    project.name = "测试工程"
    project.voltage_level = "220kV"
    project.capacity = "2×180MVA"
    project.duration_days = 180
    project.location = "某市"
    project.extra_params = json.dumps({
        "project_type": "变电站新建",
        "outline_catalog": [
            {"title": "工程概况", "level": 1},
            {"title": "施工组织设计", "level": 1},
        ],
        "outline_catalog_text": "工程概况\n施工组织设计",
    })

    req = MagicMock()
    req.id = "r1"
    req.requirement_title = "施工组织设计"
    req.score_value = 10
    req.is_risk_item = 0
    req.score_category = "施工方案"
    req.status = "confirmed"

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [req],
        [],
    ]

    skeleton = {
        "nodes": [
            {"id": "1", "title": "工程概况", "level": 1, "is_leaf": 0, "sort_order": 1},
            {"id": "2", "title": "施工组织设计", "level": 1, "is_leaf": 0, "sort_order": 2},
            {"id": "2.1", "title": "施工组织设计", "parent_id": "2", "level": 2, "is_leaf": 0, "sort_order": 1},
        ]
    }

    with patch("services.outline_service.call_llm_json", side_effect=[skeleton, RuntimeError("LLM timeout")]):
        _, _, warnings = generate_outline_ai(db, project)

    assert warnings
    assert any("展开失败" in w for w in warnings)

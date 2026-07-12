import json
import uuid

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline
from services.outline_service import (
    _merge_quality_warnings_to_nodes,
    get_outline_tree,
    get_outline_warnings,
)


def test_get_outline_tree_includes_expand_warning_from_meta():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="测试",
            extra_params=json.dumps(
                {
                    "outline_node_warnings": {
                        "leaf-1": "分支「施工组织设计」AI 展开失败，已降级为单叶子节点",
                    }
                },
                ensure_ascii=False,
            ),
        )
        db.add(project)
        db.add(
            TechOutline(
                project_id=pid,
                id="leaf-1",
                title="施工组织设计",
                sort_order=1,
                level=1,
                is_leaf=1,
            )
        )
        db.commit()

        nodes = get_outline_tree(db, pid)
        assert len(nodes) == 1
        assert nodes[0]["expand_degraded"] is True
        assert "展开失败" in nodes[0]["expand_warning"]
    finally:
        db.close()


def test_get_outline_warnings_from_meta():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="测试",
            extra_params=json.dumps(
                {"outline_warnings": ["章节「工程概况」content_boundary 未通过校验"]},
                ensure_ascii=False,
            ),
        )
        db.add(project)
        db.commit()
        warnings = get_outline_warnings(project)
        assert len(warnings) == 1
        assert "工程概况" in warnings[0]
    finally:
        db.close()


def test_merge_quality_warnings_to_nodes():
    nodes = [
        {"id": "n1", "title": "工程概况", "is_leaf": 1},
        {"id": "n2", "title": "施工方案", "is_leaf": 1},
    ]
    warnings = [
        "章节「工程概况」content_boundary 未通过校验，已替换为类型默认边界",
    ]
    merged = _merge_quality_warnings_to_nodes(nodes, warnings, {})
    assert merged["n1"] == warnings[0]
    assert "n2" not in merged

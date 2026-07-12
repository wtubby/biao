"""大纲保存时清除过期正文测试。"""

import json
import uuid

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline
from services.outline_service import save_outline_tree


def test_save_outline_tree_clears_content_when_title_changes():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        db.add(Project(id=pid, name="测试", status="planning"))
        node_id = str(uuid.uuid4())
        db.add(
            TechOutline(
                id=node_id,
                project_id=pid,
                title="旧标题",
                sort_order=1,
                level=2,
                is_leaf=1,
                requirement_ids='["req-1"]',
                writing_guidance='{"brief":"旧要点","content_boundary":"旧边界","target_words":800}',
                generated_content="旧正文",
                review_status="green",
                last_summary="旧摘要",
            )
        )
        db.commit()

        save_outline_tree(
            db,
            pid,
            [
                {
                    "id": node_id,
                    "title": "新标题",
                    "parent_id": "1",
                    "sort_order": 1,
                    "level": 2,
                    "is_leaf": 1,
                    "requirement_ids": ["req-1"],
                    "writing_guidance": '{"brief":"旧要点","content_boundary":"旧边界","target_words":800}',
                }
            ],
        )
        row = db.query(TechOutline).filter(TechOutline.id == node_id).first()
        assert row.title == "新标题"
        assert row.generated_content is None
        assert row.review_status == "init"
        assert row.last_summary is None
    finally:
        db.close()


def test_save_outline_tree_clears_content_when_requirements_change():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        db.add(Project(id=pid, name="测试", status="planning"))
        node_id = str(uuid.uuid4())
        wg = json.dumps({"brief": "要点", "content_boundary": "边界", "target_words": 600}, ensure_ascii=False)
        db.add(
            TechOutline(
                id=node_id,
                project_id=pid,
                title="施工方案",
                sort_order=1,
                level=2,
                is_leaf=1,
                requirement_ids='["req-1"]',
                writing_guidance=wg,
                generated_content="已有正文",
                review_status="green",
            )
        )
        db.commit()

        save_outline_tree(
            db,
            pid,
            [
                {
                    "id": node_id,
                    "title": "施工方案",
                    "sort_order": 1,
                    "level": 2,
                    "is_leaf": 1,
                    "requirement_ids": ["req-1", "req-2"],
                    "writing_guidance": wg,
                }
            ],
        )
        row = db.query(TechOutline).filter(TechOutline.id == node_id).first()
        assert json.loads(row.requirement_ids) == ["req-1", "req-2"]
        assert row.generated_content is None
        assert row.review_status == "init"
    finally:
        db.close()


def test_save_outline_tree_marks_new_nodes_locked_when_project_locked():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        db.add(Project(id=pid, name="测试", status="outline_locked"))
        old_id = str(uuid.uuid4())
        db.add(
            TechOutline(
                id=old_id,
                project_id=pid,
                title="已有章节",
                sort_order=1,
                level=1,
                is_leaf=1,
                is_locked=1,
            )
        )
        db.commit()
        new_id = str(uuid.uuid4())
        save_outline_tree(
            db,
            pid,
            [
                {
                    "id": old_id,
                    "title": "已有章节",
                    "sort_order": 1,
                    "level": 1,
                    "is_leaf": 1,
                },
                {
                    "id": new_id,
                    "title": "新增章节",
                    "sort_order": 2,
                    "level": 1,
                    "is_leaf": 1,
                    "guidance_brief": "新要点",
                    "content_boundary": "新边界",
                },
            ],
        )
        rows = db.query(TechOutline).filter(TechOutline.project_id == pid).all()
        assert len(rows) == 2
        assert all(r.is_locked == 1 for r in rows)
    finally:
        db.close()

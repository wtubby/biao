"""崩溃残留 generating 状态的启动恢复。"""

from datetime import datetime

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline
from services.chapter_review_errors import parse_review_errors
from services.generation_service import recover_orphaned_generations


def test_recover_orphaned_generations_resets_project_and_leaves():
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            id="p-orphan-gen",
            name="残留生成",
            status="generating",
            pause_requested=1,
            created_at=datetime(2026, 1, 1),
        )
        leaf = TechOutline(
            id="c-orphan-leaf",
            project_id=project.id,
            title="卡住章节",
            level=1,
            sort_order=0,
            is_leaf=1,
            is_locked=1,
            review_status="generating",
        )
        done_leaf = TechOutline(
            id="c-orphan-green",
            project_id=project.id,
            title="已完成",
            level=1,
            sort_order=1,
            is_leaf=1,
            is_locked=1,
            review_status="green",
        )
        db.add_all([project, leaf, done_leaf])
        db.commit()

        assert recover_orphaned_generations(db) == 1

        db.refresh(project)
        db.refresh(leaf)
        db.refresh(done_leaf)
        assert project.status == "outline_locked"
        assert project.pause_requested == 0
        assert leaf.review_status == "red"
        assert "异常中断" in " ".join(parse_review_errors(leaf.review_errors))
        assert done_leaf.review_status == "green"
    finally:
        db.query(TechOutline).filter(TechOutline.project_id == "p-orphan-gen").delete()
        db.query(Project).filter(Project.id == "p-orphan-gen").delete()
        db.commit()
        db.close()


def test_recover_orphaned_generations_noop_when_clean():
    init_db()
    db = SessionLocal()
    try:
        assert recover_orphaned_generations(db) == 0
    finally:
        db.close()

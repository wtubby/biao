"""商务标落库与 regenerate 保护。"""

from db.database import SessionLocal, init_db
from db.migrations import BID_SCOPE_TECHNICAL_COMMERCIAL
from db.models import Project
from services.commercial_bid_service import (
    STATUS_CONFIRMED,
    STATUS_DRAFT,
    get_bid_scope,
    list_commercial_sections,
    persist_commercial_draft,
    set_bid_scope,
    update_commercial_section,
)
from services.tender_detail_service import set_tender_detail


def _seed_project(db):
    project = Project(name="商务标测试工程", bid_scope="technical")
    db.add(project)
    db.flush()
    set_tender_detail(
        project,
        {
            "notice": {"project_name": "商务标测试工程", "contract_mode": "EPC", "blind_bid": False},
            "commerce_requirements": "投标保证金 10 万元。",
            "qualification_items": [
                {"seq": 1, "item_label": "资格性审查", "description": "具备承装资质"},
                {"seq": 2, "item_label": "符合性审查", "description": "响应文件齐全"},
            ],
            "commerce_scores": [
                {"title": "业绩", "criteria": "近三年同类业绩", "score_value": 10},
            ],
        },
    )
    db.commit()
    db.refresh(project)
    return project


def test_persist_commercial_sections_counts():
    init_db()
    db = SessionLocal()
    try:
        project = _seed_project(db)
        set_bid_scope(project, True)
        rows = persist_commercial_draft(db, project)
        db.commit()
        assert get_bid_scope(project) == BID_SCOPE_TECHNICAL_COMMERCIAL
        # notice + commerce_requirement + 2 qual + 1 score
        assert len(rows) == 5
        keys = [r.section_key for r in rows]
        assert keys.count("qualification") == 2
        assert keys.count("commerce_score") == 1
    finally:
        db.close()


def test_regenerate_preserves_confirmed():
    init_db()
    db = SessionLocal()
    try:
        project = _seed_project(db)
        set_bid_scope(project, True)
        rows = persist_commercial_draft(db, project)
        db.commit()
        target = next(r for r in rows if r.section_key == "commerce_requirement")
        update_commercial_section(
            db,
            project.id,
            target.id,
            content_markdown="## 人工确认内容\n\n已核对。\n",
            status=STATUS_CONFIRMED,
        )
        db.commit()

        # 改 tender_detail 后 regenerate
        set_tender_detail(
            project,
            {
                "notice": {"project_name": "商务标测试工程", "contract_mode": "EPC"},
                "commerce_requirements": "投标保证金改为 20 万元。",
                "qualification_items": [
                    {"seq": 1, "item_label": "资格性审查", "description": "具备承装资质"},
                    {"seq": 2, "item_label": "符合性审查", "description": "响应文件齐全"},
                ],
                "commerce_scores": [
                    {"title": "业绩", "criteria": "近三年同类业绩", "score_value": 10},
                ],
            },
        )
        rows2 = persist_commercial_draft(db, project, preserve_confirmed=True)
        db.commit()
        confirmed = next(r for r in rows2 if r.id == target.id)
        assert confirmed.status == STATUS_CONFIRMED
        assert "人工确认内容" in confirmed.content_markdown
        draft_rows = [r for r in rows2 if r.status == STATUS_DRAFT]
        assert draft_rows
    finally:
        db.close()

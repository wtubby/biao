"""大纲覆盖度校验测试（绑定为可选项，仅作提示）。"""

import uuid

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.outline_service import validate_coverage


def _seed_outline(db, req_statuses: list[str]):
    pid = str(uuid.uuid4())
    db.add(Project(id=pid, name="测试工程", status="planning"))
    req_ids: list[str] = []
    for i, status in enumerate(req_statuses):
        rid = str(uuid.uuid4())
        req_ids.append(rid)
        db.add(
            TechRequirement(
                id=rid,
                project_id=pid,
                requirement_title=f"评分项{i + 1}",
                score_value=10,
                status=status,
                is_risk_item=1 if i == 0 else 0,
            )
        )
    db.add(
        TechOutline(
            id="leaf-1",
            project_id=pid,
            title="已绑定章节",
            sort_order=1,
            level=1,
            is_leaf=1,
            requirement_ids=f'["{req_ids[0]}"]',
        )
    )
    db.commit()
    return pid, req_ids


def test_validate_coverage_reports_uncovered_requirement_but_passes():
    init_db()
    db = SessionLocal()
    try:
        pid, req_ids = _seed_outline(db, ["confirmed", "confirmed"])
        result = validate_coverage(db, pid)
        assert result["passed"] is True
        assert result["has_advisory_gaps"] is True
        uncovered_ids = {item["id"] for item in result["uncovered_requirements"]}
        assert req_ids[1] in uncovered_ids
    finally:
        db.close()


def test_validate_coverage_no_gaps_when_all_confirmed_bound():
    init_db()
    db = SessionLocal()
    try:
        pid, req_ids = _seed_outline(db, ["confirmed", "confirmed"])
        leaf = db.query(TechOutline).filter(TechOutline.project_id == pid).first()
        leaf.requirement_ids = f'["{req_ids[0]}", "{req_ids[1]}"]'
        db.commit()
        result = validate_coverage(db, pid)
        assert result["passed"] is True
        assert result["has_advisory_gaps"] is False
        assert result["uncovered_requirements"] == []
    finally:
        db.close()


def test_validate_coverage_allows_unbound_descriptive_leaf():
    init_db()
    db = SessionLocal()
    try:
        pid, req_ids = _seed_outline(db, ["confirmed", "confirmed"])
        leaf = db.query(TechOutline).filter(TechOutline.project_id == pid).first()
        leaf.requirement_ids = f'["{req_ids[0]}", "{req_ids[1]}"]'
        db.add(
            TechOutline(
                id="leaf-overview",
                project_id=pid,
                title="工程概况",
                sort_order=2,
                level=1,
                is_leaf=1,
                requirement_ids="[]",
            )
        )
        db.commit()
        result = validate_coverage(db, pid)
        assert result["passed"] is True
        assert any("工程概况" in item for item in result["optional_unbound_leaves"])
        assert result["unbound_leaves"] == []
    finally:
        db.close()


def test_validate_coverage_allows_unbound_construction_leaf():
    init_db()
    db = SessionLocal()
    try:
        pid, req_ids = _seed_outline(db, ["confirmed", "confirmed"])
        leaf = db.query(TechOutline).filter(TechOutline.project_id == pid).first()
        leaf.requirement_ids = f'["{req_ids[0]}", "{req_ids[1]}"]'
        db.add(
            TechOutline(
                id="leaf-plan",
                project_id=pid,
                title="施工组织设计",
                sort_order=2,
                level=1,
                is_leaf=1,
                requirement_ids="[]",
            )
        )
        db.commit()
        result = validate_coverage(db, pid)
        assert result["passed"] is True
        assert result["has_advisory_gaps"] is True
        assert any("施工组织设计" in item for item in result["unbound_leaves"])
    finally:
        db.close()

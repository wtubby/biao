"""合规终审服务测试。"""

import uuid
from datetime import datetime, timedelta, timezone

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.compliance_service import (
    check_chapter_length_balance,
    check_compliance_now,
    check_cross_consistency,
    check_scoring_coverage,
    check_title_keywords_from_outline,
    is_compliance_report_stale,
    run_compliance,
)


def _setup_project(db, content: str, duration: int = 60):
    pid = str(uuid.uuid4())
    project = Project(id=pid, name="测试工程", voltage_level="220kV", duration_days=duration, status="done")
    db.add(project)
    req = TechRequirement(
        id=str(uuid.uuid4()),
        project_id=pid,
        requirement_title="施工组织设计",
        score_value=20,
        keyword="施工组织,方案",
        status="confirmed",
    )
    db.add(req)
    ch = TechOutline(
        project_id=pid,
        id=str(uuid.uuid4()),
        title="施工组织设计",
        sort_order=1,
        level=1,
        is_leaf=1,
        requirement_ids=f'["{req.id}"]',
        generated_content=content,
    )
    db.add(ch)
    db.commit()
    return project, [ch], req


def test_cross_consistency_flags_d_plus_over_duration():
    init_db()
    db = SessionLocal()
    try:
        project, _, _ = _setup_project(db, "关键节点 D+130 完成调试", duration=60)
        items = check_cross_consistency(project, "关键节点 D+130 完成调试", {})
        assert any(i.get("level") == "fail" for i in items)
    finally:
        db.close()


def test_scoring_coverage_missing():
    init_db()
    db = SessionLocal()
    try:
        project, _, req = _setup_project(db, "与评分无关的泛泛而谈")
        results = check_scoring_coverage("与评分无关的泛泛而谈", [req])
        assert results[0]["status"] in ("missing", "partial")
    finally:
        db.close()


def test_run_compliance_without_docx():
    init_db()
    db = SessionLocal()
    try:
        project, chapters, _ = _setup_project(
            db,
            "本工程采用施工组织方案，完全响应招标文件要求，包含主变安装工序。",
        )
        report = run_compliance(db, project, None, chapters)
        assert "passed" in report
        assert "markdown" in report
        assert "施工组织" in report["markdown"]
    finally:
        db.close()


def test_check_compliance_now_without_docx():
    init_db()
    db = SessionLocal()
    try:
        project, _, _ = _setup_project(
            db,
            "本工程采用施工组织方案，完全响应招标文件要求，包含主变安装工序。",
        )
        report = check_compliance_now(db, project)
        assert "passed" in report
        assert "markdown" in report
        assert report.get("checked_at")
    finally:
        db.close()


def test_is_compliance_report_stale_after_regeneration():
    init_db()
    db = SessionLocal()
    try:
        project, chapters, _ = _setup_project(db, "初版内容")
        report = check_compliance_now(db, project)
        assert not is_compliance_report_stale(db, project, report)

        ch = chapters[0]
        ch.generated_at = datetime.now(timezone.utc) + timedelta(seconds=5)
        db.commit()
        assert is_compliance_report_stale(db, project, report)
    finally:
        db.close()


def test_cross_consistency_d_plus_soft_warn_not_fail():
    init_db()
    db = SessionLocal()
    try:
        project, _, _ = _setup_project(db, "关键节点 D+80 完成调试", duration=60)
        items = check_cross_consistency(project, "关键节点 D+80 完成调试", {})
        assert any(i.get("level") == "warn" for i in items)
        assert not any(i.get("level") == "fail" for i in items)
    finally:
        db.close()


def test_run_compliance_fails_on_coverage_missing():
    """评分项完全未响应计入 fail，不再与 partial 同级 warn。"""
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="测试", voltage_level="220kV", duration_days=60, status="done")
        db.add(project)
        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="BIM技术应用方案",
            score_value=15,
            keyword="BIM,建筑信息模型",
            status="confirmed",
        )
        db.add(req)
        ch = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="工程概况",
            sort_order=1,
            level=1,
            is_leaf=1,
            requirement_ids=f'["{req.id}"]',
            generated_content="本工程为常规土建项目概况说明，未涉及专项技术。",
        )
        db.add(ch)
        db.commit()
        report = run_compliance(db, project, None, [ch])
        assert report["passed"] is False
        assert report["failure_count"] >= 1
        assert report["coverage"][0]["status"] == "missing"
    finally:
        db.close()


def test_run_compliance_partial_coverage_is_warn_not_fail():
    """部分覆盖仍为 warn，不拉低 passed。"""
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="测试", voltage_level="220kV", duration_days=60, status="done")
        db.add(project)
        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="BIM技术应用方案",
            score_value=15,
            keyword="BIM,建筑信息模型",
            status="confirmed",
        )
        db.add(req)
        # 只命中一个候选词 → partial
        ch = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="工程概况",
            sort_order=1,
            level=1,
            is_leaf=1,
            requirement_ids=f'["{req.id}"]',
            generated_content="本工程将应用 BIM 进行协同设计。",
        )
        db.add(ch)
        db.commit()
        report = run_compliance(db, project, None, [ch])
        assert report["coverage"][0]["status"] == "partial"
        assert report["passed"] is True
        assert report["warning_count"] >= 1
        assert report["failure_count"] == 0
    finally:
        db.close()


def test_run_compliance_fails_on_template_residue():
    init_db()
    db = SessionLocal()
    try:
        project, chapters, _ = _setup_project(
            db,
            "本工程施工组织方案 TODO 待补充，包含 XXX 占位符。",
        )
        report = run_compliance(db, project, None, chapters)
        assert report["passed"] is False
        assert report["failure_count"] > 0
    finally:
        db.close()


def test_check_title_keywords_flags_bound_chapter_missing_keyword():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="测试", voltage_level="220kV", duration_days=60, status="done")
        db.add(project)
        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="质量保证措施",
            score_value=10,
            keyword="质量,保证",
            status="confirmed",
        )
        db.add(req)
        ch = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="施工组织设计",
            sort_order=1,
            level=1,
            is_leaf=1,
            requirement_ids=f'["{req.id}"]',
            generated_content="正文",
        )
        db.add(ch)
        db.commit()
        issues = check_title_keywords_from_outline([ch], [req])
        assert issues
        assert issues[0]["chapter"] == "施工组织设计"
    finally:
        db.close()


def test_run_compliance_unbound_requirement_missing_fails():
    """未绑定章节的评分项若正文完全未覆盖，同样计入 fail。"""
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="测试", voltage_level="220kV", duration_days=60, status="done")
        db.add(project)
        req_bound = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="施工组织设计",
            score_value=20,
            keyword="施工组织,方案",
            status="confirmed",
        )
        req_unbound = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="环境保护措施",
            score_value=10,
            keyword="环保,文明施工",
            status="confirmed",
        )
        db.add(req_bound)
        db.add(req_unbound)
        ch = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="施工组织设计",
            sort_order=1,
            level=1,
            is_leaf=1,
            requirement_ids=f'["{req_bound.id}"]',
            generated_content="本工程采用施工组织方案，完全响应招标文件要求，包含主变安装工序。",
        )
        db.add(ch)
        db.commit()
        report = run_compliance(db, project, None, [ch])
        assert report["passed"] is False
        assert report["failure_count"] >= 1
        missing = [c for c in report["coverage"] if c["status"] == "missing"]
        assert any(c["title"] == "环境保护措施" for c in missing)
    finally:
        db.close()


def test_scoring_coverage_covered_when_keywords_match():
    init_db()
    db = SessionLocal()
    try:
        project, _, req = _setup_project(
            db,
            "本工程采用施工组织方案，完全响应招标文件要求，包含主变安装工序。",
        )
        results = check_scoring_coverage(
            "本工程采用施工组织方案，完全响应招标文件要求，包含主变安装工序。",
            [req],
        )
        assert results[0]["status"] == "covered"
    finally:
        db.close()


def test_check_chapter_length_balance_flags_dominant_chapter():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="测试", voltage_level="220kV", duration_days=60, status="done")
        db.add(project)
        short = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="工程概况",
            sort_order=1,
            level=1,
            is_leaf=1,
            generated_content="简短概况。",
        )
        long = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="施工组织设计",
            sort_order=2,
            level=1,
            is_leaf=1,
            generated_content="详细方案。" * 200,
        )
        db.add(short)
        db.add(long)
        db.commit()

        issues = check_chapter_length_balance([short, long])
        assert issues
        assert any("施工组织设计" in i["message"] for i in issues)
        assert all(i["level"] == "warn" for i in issues)
    finally:
        db.close()

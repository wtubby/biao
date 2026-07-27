"""可插拔检查注册表与废标条款对照测试。"""

from __future__ import annotations

import uuid

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.check_catalog import list_categories
from services.check_registry import (
    ChapterCheckContext,
    findings_to_messages,
    list_checks,
    reset_registry_for_tests,
    run_chapter_checks,
    summarize_findings,
)
from services.check_skills import check_disqualification_risks
from services.chapter_qa_orchestrator import run_hard_qa
from services.compliance_service import run_compliance
from services.project_meta import set_meta


def test_catalog_has_core_categories():
    cats = {c["id"] for c in list_categories()}
    assert "template_residue" in cats
    assert "disqualification_risk" in cats
    assert "scoring_coverage" in cats
    assert len(cats) >= 15


def test_builtin_chapter_checks_registered():
    reset_registry_for_tests()
    skills = list_checks(scope="chapter")
    ids = {s.check_id for s in skills}
    assert "template_residue" in ids
    assert "scoring_coverage" in ids
    assert "fabricated_standards" in ids


def test_run_hard_qa_via_registry_flags_template():
    reset_registry_for_tests()
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="检查改造", status="generating", duration_days=60)
        db.add(project)
        db.commit()
        errors = run_hard_qa(
            "本工程采用 XXX公司 方案完成施工。",
            project,
            [],
            {"target_words": 200},
            chapter_title="施工组织设计",
        )
        assert any("XXX" in e or "模板" in e or "残留" in e or "占位" in e for e in errors)
    finally:
        db.close()


def test_chapter_findings_summary():
    reset_registry_for_tests()
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="摘要", status="generating", duration_days=60)
        db.add(project)
        db.commit()
        findings = run_chapter_checks(
            ChapterCheckContext(
                content="本方案由【待补充】完善。",
                project=project,
                requirements=[],
                guidance={"target_words": 50},
                chapter_title="施工方案",
                scope="chapter",
            )
        )
        msgs = findings_to_messages(findings)
        assert msgs
        summary = summarize_findings(findings)
        assert summary["block_count"] >= 1
        assert "template_residue" in summary["by_category"]
    finally:
        db.close()


def test_disqualification_risks_escalates_on_template():
    findings = check_disqualification_risks(
        "投标方案由 XXX公司 编制。",
        [
            {
                "seq": 1,
                "item_label": "废标",
                "description": "技术标出现投标人名称或未实质性响应的，按废标处理",
            }
        ],
    )
    assert findings
    assert any(f.severity == "block" for f in findings)


def test_disqualification_risks_manual_review_warn():
    findings = check_disqualification_risks(
        "本工程采用成熟工艺完成主变安装，完全响应招标文件要求。",
        [
            {
                "seq": 2,
                "item_label": "废标",
                "description": "技术方案存在负偏离或漏项的，作废标处理",
            }
        ],
    )
    assert findings
    assert all(f.severity in ("warn", "info") for f in findings)


def test_run_compliance_includes_findings_and_disqual_section():
    reset_registry_for_tests()
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="合规改造", voltage_level="220kV", duration_days=60, status="done")
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
            generated_content="本工程采用施工组织方案，完全响应招标文件要求，包含主变安装工序。",
        )
        db.add(ch)
        set_meta(
            project,
            tender_detail={
                "qualification_items": [
                    {
                        "seq": 1,
                        "item_label": "废标情形",
                        "description": "未实质性响应或出现漏项的作废标处理",
                    }
                ]
            },
        )
        db.commit()
        report = run_compliance(db, project, None, [ch])
        assert "findings" in report
        assert "category_summary" in report
        assert "九、废标条款对照" in report["sections"]
        assert "检查分类汇总" in report["markdown"]
    finally:
        db.close()


def test_fabricated_standards_check_passes_db_session(monkeypatch):
    """_standards 经 object_session(ctx.project) 取得活跃 session，db 不为 None。"""
    reset_registry_for_tests()
    init_db()
    db = SessionLocal()
    captured: dict = {}

    def _spy(content, allowed_sources, *, domain=None, db=None):
        captured["db"] = db
        return []

    monkeypatch.setattr("services.check_skills.collect_fabricated_standards", _spy)
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="标准库会话", status="generating", duration_days=60)
        db.add(project)
        db.commit()
        findings = run_chapter_checks(
            ChapterCheckContext(
                content="施工按 GB/T 99999-2099 执行。",
                project=project,
                requirements=[],
                guidance={"target_words": 50},
                chapter_title="施工方案",
                allowed_standard_sources="",
                scope="chapter",
            )
        )
        assert captured.get("db") is not None
        assert captured["db"] is db
        assert findings is not None
    finally:
        db.close()

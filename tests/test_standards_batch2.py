"""推荐标准注入与标准时效性项目级检查。"""

from __future__ import annotations

import uuid

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline
from services.check_catalog import list_categories
from services.check_registry import (
    ProjectCheckContext,
    ensure_builtin_checks_registered,
    reset_registry_for_tests,
    run_project_checks,
)
from services.project_meta import set_meta
from services.qa_rules import normalize_standard_core
from services.standards_service import link_domains, upsert_standard


def test_build_context_bundle_includes_recommended_standards(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="推荐标准", status="generating", duration_days=60)
        db.add(project)
        chapter = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="电缆敷设施工方案",
            sort_order=1,
            level=1,
            is_leaf=1,
            requirement_ids="[]",
        )
        db.add(chapter)
        set_meta(project, engineering_domain="电力工程")
        db.commit()

        n1 = 85000 + (uuid.uuid4().int % 900)
        n2 = 86000 + (uuid.uuid4().int % 900)
        raw1, raw2 = f"GB/T {n1}", f"GB/T {n2}"
        c1 = normalize_standard_core(raw1)
        c2 = normalize_standard_core(raw2)
        upsert_standard(
            db, code=c1, raw_code=raw1, title="电力电缆敷设规范", status="active", summary="电缆敷设要求",
        )
        upsert_standard(
            db, code=c2, raw_code=raw2, title="电力工程验收规范", status="active",
        )
        link_domains(db, c1, ["电力工程"])
        link_domains(db, c2, ["电力工程"])

        monkeypatch.setattr(
            "services.chapter_context_service.retrieve_detailed",
            lambda *a, **k: __import__(
                "services.retrieval_service", fromlist=["RetrievalResult"]
            ).RetrievalResult(chunks=[], empty_reason="no_match"),
        )
        monkeypatch.setattr(
            "services.chapter_context_service.get_generation_config",
            lambda _p: {"use_knowledge_library": False, "standards_pack": "epc_guide"},
        )

        from services.chapter_context_service import build_context_bundle

        bundle = build_context_bundle(db, project, chapter)
        text = bundle.get("recommended_standards_text") or ""
        assert text.strip()
        assert raw1 in text or c1 in text
        assert "仅供参考" in text
    finally:
        db.close()


def test_standards_currency_category_registered():
    cats = {c["id"] for c in list_categories()}
    assert "standards_currency" in cats


def test_project_standards_currency_flags_withdrawn():
    reset_registry_for_tests()
    ensure_builtin_checks_registered()
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="时效性", status="done", duration_days=60)
        db.add(project)
        n = 87000 + (uuid.uuid4().int % 900)
        raw = f"GB/T {n}"
        core = normalize_standard_core(raw)
        upsert_standard(db, code=core, raw_code=raw, title="废止测试标准", status="withdrawn")
        ch = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="施工方案",
            sort_order=1,
            level=1,
            is_leaf=1,
            generated_content=f"本工程按 {raw}-1999 执行电缆敷设。",
        )
        db.add(ch)
        set_meta(project, engineering_domain="电力工程")
        db.commit()

        findings = run_project_checks(
            ProjectCheckContext(
                project=project,
                chapters=[ch],
                requirements=[],
                docx_text=ch.generated_content or "",
            )
        )
        currency = [f for f in findings if f.check_id == "project_standards_currency"]
        assert currency
        assert any("已废止" in f.message for f in currency)
    finally:
        db.close()

"""写作服务单元测试。"""

import json
import sys
import uuid
from unittest.mock import MagicMock, patch

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.writer_service import (
    build_context_bundle,
    estimate_chapter_max_tokens,
    run_hard_qa,
    run_soft_qa,
    write_and_qa_chapter,
)


def _seed_write_chapter(db, *, target_words: int = 800, domain: str = "电力工程"):
    pid = str(uuid.uuid4())
    project = Project(
        id=pid,
        name="测试变电站工程",
        voltage_level="220kV",
        duration_days=180,
        status="outline_locked",
    )
    db.add(project)
    req = TechRequirement(
        id=str(uuid.uuid4()),
        project_id=pid,
        requirement_title="施工组织设计",
        score_value=10,
        keyword="施工组织",
        status="confirmed",
    )
    db.add(req)
    wg = json.dumps(
        {"brief": "写施工组织", "content_boundary": "写组织方案", "target_words": target_words},
        ensure_ascii=False,
    )
    chapter = TechOutline(
        id=str(uuid.uuid4()),
        project_id=pid,
        title="施工组织设计",
        sort_order=1,
        level=1,
        is_leaf=1,
        requirement_ids=f'["{req.id}"]',
        writing_guidance=wg,
        is_locked=1,
    )
    db.add(chapter)
    db.commit()
    return project, chapter, req


def _long_technical_content():
    return (
        "本工程施工组织设计针对220kV变电站新建工程，总工期180日历天。"
        "施工组织方案包括人员配置12人、机械投入3台、关键工序质量控制点15处，"
        "混凝土浇筑方量约1200立方米，电缆敷设长度约3.5公里。"
        "完全响应招标文件施工组织设计要求，落实三级质检体系与24小时值班制度。"
    ) * 8


def test_estimate_chapter_max_tokens_none_uses_default(monkeypatch):
    monkeypatch.setattr("config.LLM_MAX_TOKENS", 4096)
    monkeypatch.setattr("config.LLM_MAX_TOKENS_CEILING", 8000)
    assert estimate_chapter_max_tokens(None) == 4096


def test_estimate_chapter_max_tokens_small_clamped_to_default(monkeypatch):
    monkeypatch.setattr("config.LLM_MAX_TOKENS", 4096)
    monkeypatch.setattr("config.LLM_MAX_TOKENS_CEILING", 8000)
    monkeypatch.setattr("config.CHARS_PER_TOKEN_CN", 0.6)
    assert estimate_chapter_max_tokens(100) == 4096


def test_estimate_chapter_max_tokens_large_clamped_to_ceiling(monkeypatch):
    monkeypatch.setattr("config.LLM_MAX_TOKENS", 4096)
    monkeypatch.setattr("config.LLM_MAX_TOKENS_CEILING", 8000)
    monkeypatch.setattr("config.CHARS_PER_TOKEN_CN", 0.6)
    assert estimate_chapter_max_tokens(10000) == 8000


def test_estimate_chapter_max_tokens_mid_range(monkeypatch):
    monkeypatch.setattr("config.LLM_MAX_TOKENS", 4096)
    monkeypatch.setattr("config.LLM_MAX_TOKENS_CEILING", 8000)
    monkeypatch.setattr("config.CHARS_PER_TOKEN_CN", 0.6)
    assert estimate_chapter_max_tokens(3000) == 5500


def test_run_soft_qa_network_failure_skipped(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("network timeout")

    monkeypatch.setattr("services.chapter_qa_orchestrator.call_llm_json", _raise)
    result = run_soft_qa(
        "正文内容",
        {
            "chapter_title": "施工组织设计",
            "chapter_path": "施工组织设计",
            "requirements_text": "施工组织方案",
            "retrieval_text": "",
            "sibling_leaf_titles": [],
        },
    )

    assert result["passed"] is False
    assert result.get("skipped") is True
    assert "network timeout" in result.get("skip_reason", "")


def test_run_hard_qa_flags_content_too_short(monkeypatch):
    monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MIN_RATIO", 0.75)
    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    content = "施工组织方案概述。" * 10
    errors = run_hard_qa(
        content,
        project,
        [],
        {"target_words": 1000},
        chapter_title="施工组织设计",
    )
    assert any("篇幅不足" in e for e in errors)


def test_run_hard_qa_flags_fabricated_standards(monkeypatch):
    monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MIN_RATIO", 0.01)
    monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MAX_RATIO", 100.0)
    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    content = (
        "本工程220kV变电站施工组织设计，总工期180日历天。"
        "施工按虚构规范 GB/T 99999-2099 执行，配置人员12人、机械3台。"
    ) * 5
    errors = run_hard_qa(
        content,
        project,
        [],
        {"target_words": 200},
        chapter_title="施工组织设计",
        allowed_standard_sources="无标准号来源",
    )
    assert any("编造" in e or "标准号" in e for e in errors)


def test_run_hard_qa_flags_plan_coverage(monkeypatch):
    monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MIN_RATIO", 0.01)
    monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MAX_RATIO", 100.0)
    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    content = (
        "本工程220kV变电站施工组织设计，总工期180日历天。"
        "本章仅概述一般管理要求与人员配置12人。"
    ) * 6
    errors = run_hard_qa(
        content,
        project,
        [],
        {"target_words": 200},
        chapter_title="施工组织设计",
        content_plan={
            "key_points": ["主变吊装双机抬吊", "GIS交接试验", "电缆耐压", "接地网测试"],
        },
    )
    assert any("要点覆盖" in e for e in errors)


def test_build_context_bundle_empty_retrieval_text(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, domain="市政工程")
        retrieval = type("R", (), {
            "chunks": [],
            "empty_reason": "knowledge_empty",
            "knowledge_available": False,
        })()

        with patch("services.chapter_context_service.get_meta", return_value={"engineering_domain": "市政工程"}), patch(
            "services.chapter_context_service.retrieve_detailed",
            return_value=retrieval,
        ):
            bundle = build_context_bundle(db, project, chapter)

        assert bundle["retrieval_text"] == ""
        assert bundle["retrieval_warning"]
        assert "补充说明" not in bundle["global_params"]
        assert bundle.get("project_overview") is None
    finally:
        db.close()


def test_write_and_qa_chapter_retries_on_hard_qa_then_green(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=800)
        hard_calls = {"n": 0}

        def fake_hard_qa(*_args, **_kwargs):
            hard_calls["n"] += 1
            if hard_calls["n"] == 1:
                return ["篇幅不足：当前约 10 字，目标 800 字（下限 600）"]
            return []

        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=(_long_technical_content(), None),
        ), patch("services.chapter_qa_orchestrator.run_hard_qa", side_effect=fake_hard_qa), patch(
            "services.chapter_qa_orchestrator.run_soft_qa",
            return_value={"passed": True},
        ), patch("services.chapter_qa_orchestrator.generate_summary", return_value="摘要"), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            result, _, warning = write_and_qa_chapter(db, project, chapter)

        assert hard_calls["n"] == 2
        assert result.review_status == "green"
        assert result.retry_count == 1
        assert warning is None
    finally:
        db.close()


def test_write_and_qa_chapter_hard_qa_exhausted_sets_yellow(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=1200)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY", 1)

        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=("过短正文。", None),
        ), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            result, _, _ = write_and_qa_chapter(db, project, chapter)

        assert result.review_status == "yellow"
        errors = json.loads(result.review_errors)
        assert any("篇幅不足" in e for e in errors)
        assert result.retry_count >= 1
    finally:
        db.close()


def test_write_and_qa_chapter_soft_qa_failure_sets_yellow(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=5000)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY", 0)
        monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MIN_RATIO", 0.01)
        monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MAX_RATIO", 100.0)

        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=(_long_technical_content(), None),
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa",
            return_value=[],
        ), patch(
            "services.chapter_qa_orchestrator.run_soft_qa",
            return_value={
                "passed": False,
                "coverage_issues": ["未覆盖评分要点A"],
                "faithfulness_issues": [],
                "scope_issues": [],
            },
        ), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            result, _, _ = write_and_qa_chapter(db, project, chapter)

        assert result.review_status == "yellow"
        errors = json.loads(result.review_errors)
        assert "未覆盖评分要点A" in errors
    finally:
        db.close()


def test_write_and_qa_chapter_soft_qa_skipped_sets_yellow(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=5000)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MIN_RATIO", 0.01)
        monkeypatch.setattr("services.chapter_qa_orchestrator.WORD_COUNT_MAX_RATIO", 100.0)

        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=(_long_technical_content(), None),
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa",
            return_value=[],
        ), patch(
            "services.chapter_qa_orchestrator.run_soft_qa",
            return_value={
                "passed": False,
                "skipped": True,
                "skip_reason": "network timeout",
            },
        ), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.chapter_qa_orchestrator.generate_summary",
            return_value="摘要",
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            result, _, _ = write_and_qa_chapter(db, project, chapter)

        assert result.review_status == "yellow"
        errors = json.loads(result.review_errors)
        assert any("软质检未执行" in e for e in errors)
    finally:
        db.close()

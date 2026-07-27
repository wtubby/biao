"""写作服务单元测试。"""

import json
import sys
import uuid
from unittest.mock import MagicMock, patch

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.chapter_qa_orchestrator import (
    _apply_qa_result_to_chapter,
    _run_chapter_qa,
    run_hard_qa_all_findings,
)
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


def test_run_hard_qa_does_not_block_on_warn_word_count(monkeypatch):
    """篇幅不足是 warn：不作为硬错误触发重写。"""
    monkeypatch.setattr("config.WORD_COUNT_MIN_RATIO", 0.75)
    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    content = "施工组织方案概述。" * 10
    assert run_hard_qa(
        content,
        project,
        [],
        {"target_words": 1000},
        chapter_title="施工组织设计",
    ) == []
    findings = run_hard_qa_all_findings(
        content,
        project,
        [],
        {"target_words": 1000},
        chapter_title="施工组织设计",
    )
    assert any(f.severity == "warn" and "篇幅不足" in f.message for f in findings)


def test_run_hard_qa_flags_fabricated_standards(monkeypatch):
    monkeypatch.setattr("config.WORD_COUNT_MIN_RATIO", 0.01)
    monkeypatch.setattr("config.WORD_COUNT_MAX_RATIO", 100.0)
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


def test_run_hard_qa_does_not_block_on_warn_plan_coverage(monkeypatch):
    """规划要点覆盖不足是 warn：不作为硬错误触发重写。"""
    monkeypatch.setattr("config.WORD_COUNT_MIN_RATIO", 0.01)
    monkeypatch.setattr("config.WORD_COUNT_MAX_RATIO", 100.0)
    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    content = (
        "本工程220kV变电站施工组织设计，总工期180日历天。"
        "本章仅概述一般管理要求与人员配置12人。"
    ) * 6
    assert run_hard_qa(
        content,
        project,
        [],
        {"target_words": 200},
        chapter_title="施工组织设计",
        content_plan={
            "key_points": ["主变吊装双机抬吊", "GIS交接试验", "电缆耐压", "接地网测试"],
        },
    ) == []
    findings = run_hard_qa_all_findings(
        content,
        project,
        [],
        {"target_words": 200},
        chapter_title="施工组织设计",
        content_plan={
            "key_points": ["主变吊装双机抬吊", "GIS交接试验", "电缆耐压", "接地网测试"],
        },
    )
    assert any(f.severity == "warn" and "要点覆盖" in f.message for f in findings)


def test_run_chapter_qa_routes_warn_to_extra_warn_issues(monkeypatch):
    """warn 级发现进入 soft.extra_warn_issues，不返回 hard_errors。"""
    monkeypatch.setattr("config.WORD_COUNT_MIN_RATIO", 0.75)
    monkeypatch.setattr(
        "services.chapter_qa_orchestrator.run_soft_qa",
        lambda *_a, **_k: {"passed": True, "coverage_issues": [], "faithfulness_issues": [],
                            "scope_issues": [], "specificity_issues": []},
    )
    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    chapter = TechOutline(id="c1", project_id="p1", title="施工组织设计", sort_order=1, level=1, is_leaf=1)
    content = "施工组织方案概述。" * 10
    hard, soft = _run_chapter_qa(
        content,
        project,
        chapter,
        {
            "guidance": {"target_words": 1000},
            "requirements": [],
            "other_leaf_titles": [],
        },
    )
    assert hard == []
    assert any("篇幅不足" in m for m in soft.get("extra_warn_issues") or [])

    _apply_qa_result_to_chapter(chapter, content, hard_errors=[], soft=soft, refresh_summary=False)
    assert chapter.review_status == "yellow"
    assert "篇幅不足" in (chapter.review_errors or "")


def test_run_segment_qa_routes_warn_without_hard_retry(monkeypatch):
    """分段质检：warn（如 plan_coverage）进 extra_warn_issues，不触发 hard。"""
    from services.chapter_qa_orchestrator import run_segment_qa

    monkeypatch.setattr(
        "services.chapter_qa_orchestrator._run_soft_qa_once",
        lambda *_a, **_k: {
            "passed": True,
            "coverage_issues": [],
            "faithfulness_issues": [],
            "scope_issues": [],
            "specificity_issues": [],
        },
    )
    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    chapter = TechOutline(id="c1", project_id="p1", title="施工组织设计", sort_order=1, level=1, is_leaf=1)
    content = (
        "本工程220kV变电站施工组织设计，总工期180日历天。"
        "本章仅概述一般管理要求与人员配置12人。"
    ) * 4
    hard, soft = run_segment_qa(
        content,
        project,
        chapter,
        {"guidance": {}, "requirements": [], "other_leaf_titles": []},
        segment_label="第1/2段",
        content_plan={
            "key_points": ["主变吊装双机抬吊", "GIS交接试验", "电缆耐压", "接地网测试"],
        },
    )
    assert hard == []
    assert any("要点覆盖" in m for m in soft.get("extra_warn_issues") or [])


def test_run_segment_qa_blocks_on_template_residue(monkeypatch):
    from services.chapter_qa_orchestrator import run_segment_qa

    project = Project(id="p1", name="测试", voltage_level="220kV", duration_days=180)
    chapter = TechOutline(id="c1", project_id="p1", title="施工组织设计", sort_order=1, level=1, is_leaf=1)
    hard, soft = run_segment_qa(
        "本工程采用 XXX公司 方案完成施工。",
        project,
        chapter,
        {"guidance": {}, "requirements": [], "other_leaf_titles": []},
        segment_label="第1/2段",
    )
    assert hard
    assert any("XXX" in e or "模板" in e or "残留" in e or "占位" in e for e in hard)
    assert soft == {}


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

        def fake_all_findings(*_args, **_kwargs):
            from services.check_registry import Finding

            hard_calls["n"] += 1
            if hard_calls["n"] == 1:
                return [
                    Finding(
                        check_id="template_residue",
                        category="template_residue",
                        severity="block",
                        message="检测到模板残留：XXX",
                    )
                ]
            return []

        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=(_long_technical_content(), None),
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            side_effect=fake_all_findings,
        ), patch(
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

        def fake_block_findings(*_args, **_kwargs):
            from services.check_registry import Finding

            return [
                Finding(
                    check_id="fabricated_standards",
                    category="fabricated_standards",
                    severity="block",
                    message="疑似编造标准号 GB/T 99999-2099",
                )
            ]

        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=("过短正文。", None),
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            side_effect=fake_block_findings,
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
        assert any("编造" in e or "标准号" in e for e in errors)
        assert result.retry_count >= 1
    finally:
        db.close()


def test_write_and_qa_chapter_warn_only_sets_yellow_without_retry(monkeypatch):
    """纯 warn 级发现：标黄但不消耗硬质检重试。"""
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=1200)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY", 2)

        def fake_warn_findings(*_args, **_kwargs):
            from services.check_registry import Finding

            return [
                Finding(
                    check_id="word_count",
                    category="word_count",
                    severity="warn",
                    message="篇幅不足：当前约 10 字，目标 1200 字（下限 900）",
                )
            ]

        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=("过短正文。", None),
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            side_effect=fake_warn_findings,
        ), patch(
            "services.chapter_qa_orchestrator.run_soft_qa",
            return_value={"passed": True},
        ), patch(
            "services.chapter_qa_orchestrator.generate_summary",
            return_value="摘要",
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
        assert result.retry_count == 0
    finally:
        db.close()


def test_write_and_qa_chapter_soft_qa_failure_sets_yellow(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=5000)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY", 0)
        monkeypatch.setattr("config.WORD_COUNT_MIN_RATIO", 0.01)
        monkeypatch.setattr("config.WORD_COUNT_MAX_RATIO", 100.0)

        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=(_long_technical_content(), None),
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
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
        monkeypatch.setattr("config.WORD_COUNT_MIN_RATIO", 0.01)
        monkeypatch.setattr("config.WORD_COUNT_MAX_RATIO", 100.0)

        with patch(
            "services.writer_service.generate_chapter_content",
            return_value=(_long_technical_content(), None),
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
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


def test_write_and_qa_chapter_budget_exhausted_sets_yellow_hint(monkeypatch):
    """Writer 预算触顶后停止外层重试，并提示已达上限。"""
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=800)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY", 3)
        monkeypatch.setattr("services.writer_service.MAX_CHAPTER_WRITER_LLM_CALLS", 2)
        gen_calls = {"n": 0}

        def fake_gen(bundle, fix_instructions=None, chat_messages=None, use_chat=False, qa_context=None):
            gen_calls["n"] += 1
            if qa_context is not None:
                qa_context["writer_llm_calls"] = qa_context.get("writer_llm_budget", 2)
                qa_context["writer_budget_exhausted"] = True
            return (_long_technical_content(), None)

        def fake_block(*_a, **_k):
            from services.check_registry import Finding

            return [
                Finding(
                    check_id="template_residue",
                    category="template_residue",
                    severity="block",
                    message="检测到模板残留：XXX",
                    evidence="XXX",
                )
            ]

        with patch(
            "services.writer_service.generate_chapter_content",
            side_effect=fake_gen,
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            side_effect=fake_block,
        ), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            result, _, _ = write_and_qa_chapter(db, project, chapter)

        assert gen_calls["n"] == 1
        assert result.review_status == "yellow"
        errors = json.loads(result.review_errors)
        assert any("已达质检重试上限" in e for e in errors)
    finally:
        db.close()


def test_write_and_qa_chapter_segmented_uses_lower_outer_retry(monkeypatch):
    """分段章外层重试使用 MAX_QA_RETRY_SEGMENTED，而非 MAX_QA_RETRY。"""
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=2000)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY", 5)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY_SEGMENTED", 1)
        monkeypatch.setattr(
            "services.writer_service._should_segment_chapter",
            lambda _bundle: True,
        )
        gen_calls = {"n": 0}

        def fake_gen(*_a, **_k):
            gen_calls["n"] += 1
            return (_long_technical_content(), None)

        def fake_block(*_a, **_k):
            from services.check_registry import Finding

            return [
                Finding(
                    check_id="fabricated_standards",
                    category="fabricated_standards",
                    severity="block",
                    message="疑似编造规范标准号：GB/T 99999-2099",
                    evidence="GB/T 99999-2099",
                )
            ]

        with patch(
            "services.writer_service.generate_chapter_content",
            side_effect=fake_gen,
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            side_effect=fake_block,
        ), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            result, _, _ = write_and_qa_chapter(db, project, chapter)

        # 1 次初写 + 1 次外层重试
        assert gen_calls["n"] == 2
        assert result.retry_count == 1
        assert result.review_status == "yellow"
    finally:
        db.close()


def test_write_and_qa_chapter_retry_includes_previous_draft(monkeypatch):
    """非分段普通章：外层重试的 fix_instructions 应附带上一版正文做定向修正。"""
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=800)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY", 1)
        monkeypatch.setattr(
            "services.writer_service._should_segment_chapter",
            lambda _bundle: False,
        )
        monkeypatch.setattr(
            "services.writer_service._is_key_chapter",
            lambda *_a, **_k: False,
        )
        draft_v1 = "上一版正文含编造标准 GB/T 99999-2099。"
        captured: list[str | None] = []

        def fake_gen(_bundle, fix_instructions=None, **_kwargs):
            captured.append(fix_instructions)
            if fix_instructions:
                return ("修正后的合格正文。", None)
            return (draft_v1, None)

        hard_n = {"n": 0}

        def fake_block(*_a, **_k):
            from services.check_registry import Finding

            hard_n["n"] += 1
            if hard_n["n"] == 1:
                return [
                    Finding(
                        check_id="fabricated_standards",
                        category="fabricated_standards",
                        severity="block",
                        message="疑似编造规范标准号：GB/T 99999-2099",
                        evidence="GB/T 99999-2099",
                    )
                ]
            return []

        with patch(
            "services.writer_service.generate_chapter_content",
            side_effect=fake_gen,
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            side_effect=fake_block,
        ), patch(
            "services.chapter_qa_orchestrator.run_soft_qa",
            return_value={"passed": True},
        ), patch(
            "services.chapter_qa_orchestrator.generate_summary",
            return_value="摘要",
        ), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            result, _, _ = write_and_qa_chapter(db, project, chapter)

        assert len(captured) == 2
        assert captured[0] is None
        assert draft_v1 in (captured[1] or "")
        assert "定向修正" in (captured[1] or "")
        assert "GB/T 99999-2099" in (captured[1] or "")
        assert result.review_status == "green"
        assert result.retry_count == 1
    finally:
        db.close()


def test_write_and_qa_chapter_segmented_retry_skips_full_draft(monkeypatch):
    """分段章外层重试不把整章正文塞进 fix_instructions（由按段复用喂单段原文）。"""
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=2000)
        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        monkeypatch.setattr("services.writer_service.MAX_QA_RETRY_SEGMENTED", 1)
        monkeypatch.setattr(
            "services.writer_service._should_segment_chapter",
            lambda _bundle: True,
        )
        long_draft = "分段章很长的正文内容。" * 20
        captured: list[str | None] = []

        def fake_gen(_bundle, fix_instructions=None, **_kwargs):
            captured.append(fix_instructions)
            return (long_draft, None)

        def fake_block(*_a, **_k):
            from services.check_registry import Finding

            return [
                Finding(
                    check_id="fabricated_standards",
                    category="fabricated_standards",
                    severity="block",
                    message="疑似编造规范标准号：GB/T 99999-2099",
                    evidence="GB/T 99999-2099",
                )
            ]

        with patch(
            "services.writer_service.generate_chapter_content",
            side_effect=fake_gen,
        ), patch(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            side_effect=fake_block,
        ), patch(
            "services.writer_service.humanize_content",
            side_effect=lambda x, deep=False: x,
        ), patch(
            "services.writer_service.capture_generation_prompt_debug",
            return_value="{}",
        ):
            write_and_qa_chapter(db, project, chapter)

        assert len(captured) == 2
        assert captured[0] is None
        assert long_draft not in (captured[1] or "")
        assert (captured[1] or "").startswith("修复以下问题：")
    finally:
        db.close()


def test_run_chapter_qa_sets_fix_anchors_from_evidence(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        project, chapter, _ = _seed_write_chapter(db, target_words=800)
        bundle = {
            "guidance": {"target_words": 800},
            "requirements": [],
            "other_leaf_titles": [],
            "retrieval_text": "",
            "global_facts_text": "",
            "requirements_text": "",
            "project_overview": "",
            "reference_bid_text": "",
            "global_params": {},
        }
        qa_context: dict = {}

        def fake_findings(*_a, **_k):
            from services.check_registry import Finding

            return [
                Finding(
                    check_id="fabricated_standards",
                    category="fabricated_standards",
                    severity="block",
                    message="疑似编造规范标准号：GB/T 99999-2099",
                    evidence="GB/T 99999-2099",
                )
            ]

        monkeypatch.setattr(
            "services.chapter_qa_orchestrator.run_hard_qa_all_findings",
            fake_findings,
        )
        hard, soft = _run_chapter_qa(
            "正文含 GB/T 99999-2099",
            project,
            chapter,
            bundle,
            qa_context=qa_context,
        )
        assert hard
        assert qa_context["fix_anchors"] == ["GB/T 99999-2099"]
        assert soft == {}
    finally:
        db.close()

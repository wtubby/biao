"""中优先级生成质量增强单元测试。"""

import sys
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from prompts.qa_prompt import QA_SYSTEM_PROMPT
from prompts.writer_prompt import build_writer_user_prompt
from services.requirement_prompt import build_chapter_evaluation_focus
from services.writing_guidance import should_skip_content_plan
from services.writer_service import resolve_content_plan, run_soft_qa


def _req(**kwargs):
    base = dict(
        id="r1",
        requirement_title="GIS 安装调试",
        score_value=10.0,
        is_risk_item=0,
        keyword="GIS,交接试验",
        mandatory_elements="交接试验",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_should_skip_content_plan_for_descriptive_chapter():
    bundle = {
        "chapter_title": "工程概况",
        "guidance": {"target_words": 2000},
    }
    assert should_skip_content_plan(bundle) is True


def test_should_skip_content_plan_for_low_word_target():
    bundle = {
        "chapter_title": "施工部署",
        "guidance": {"target_words": 400},
    }
    assert should_skip_content_plan(bundle, word_threshold=500) is True


def test_should_not_skip_content_plan_for_long_construction_chapter():
    bundle = {
        "chapter_title": "GIS 安装调试",
        "guidance": {"target_words": 1200},
    }
    assert should_skip_content_plan(bundle, word_threshold=500) is False


def test_build_chapter_evaluation_focus_lists_requirements_and_project():
    text = build_chapter_evaluation_focus(
        "GIS 安装调试",
        [_req(is_risk_item=1, score_value=12)],
        {"工程名称": "某变电站", "电压等级": "220kV", "总工期": 180},
    )
    assert "本章评标关注点" in text
    assert "GIS" in text
    assert "交接试验" in text
    assert "220kV" in text
    assert "通稿套话" in text


def test_build_chapter_evaluation_focus_skips_descriptive():
    assert build_chapter_evaluation_focus("项目质量目标", [_req()], {}) == ""


def test_resolve_content_plan_uses_fallback_without_llm(monkeypatch):
    called = {"llm": False}

    def fake_generate(_bundle):
        called["llm"] = True
        return {"key_points": ["a"]}

    monkeypatch.setattr("services.chapter_generation_service.generate_content_plan", fake_generate)
    bundle = {
        "chapter_title": "工程概况",
        "guidance": {"target_words": 600},
        "requirements_text": "",
        "chapter_path": "概况",
    }
    plan = resolve_content_plan(bundle)
    assert called["llm"] is False
    assert plan.get("key_points")


def test_run_soft_qa_merges_specificity_issues(monkeypatch):
    monkeypatch.setattr(
        "services.chapter_qa_orchestrator._run_soft_qa_once",
        lambda *_a, **_k: {
            "passed": False,
            "coverage_issues": [],
            "faithfulness_issues": [],
            "scope_issues": [],
            "specificity_issues": ["正文像通用模板，未体现本项目电压等级"],
        },
    )
    monkeypatch.setattr(
        "services.chapter_qa_orchestrator.sample_content_windows_for_qa",
        lambda _c: [("全文", "正文")],
    )
    result = run_soft_qa("正文", {"chapter_title": "施工方案"})
    assert result["specificity_issues"]
    assert "电压等级" in result["specificity_issues"][0]


def test_qa_system_prompt_includes_specificity_dimension():
    assert "specificity_issues" in QA_SYSTEM_PROMPT
    assert "针对性" in QA_SYSTEM_PROMPT


def test_writer_prompt_includes_evaluation_focus():
    prompt = build_writer_user_prompt(
        {
            "global_params": {"工程名称": "测试", "电压等级": "220kV"},
            "requirements_text": "评分项",
            "retrieval_text": "",
            "chapter_title": "GIS 安装",
            "chapter_level": 2,
            "chapter_path": "方案 > GIS 安装",
            "guidance": {"brief": "写安装", "content_boundary": "写工序", "target_words": 800},
            "evaluation_focus": "【本章评标关注点】\n- [10分] GIS 安装调试：关键词：GIS",
            "sibling_leaf_titles": [],
            "other_leaf_titles": [],
        }
    )
    assert "本章评标关注点" in prompt
    assert "GIS" in prompt


def test_build_context_bundle_includes_evaluation_focus():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="测试工程",
            voltage_level="220kV",
            duration_days=180,
            location="成都",
            status="outline_locked",
        )
        db.add(project)
        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="施工组织设计",
            score_value=12,
            keyword="施工组织",
            mandatory_elements="三级网络计划",
            status="confirmed",
        )
        db.add(req)
        chapter = TechOutline(
            id=str(uuid.uuid4()),
            project_id=pid,
            title="施工组织设计",
            sort_order=1,
            level=1,
            is_leaf=1,
            requirement_ids=f'["{req.id}"]',
            writing_guidance='{"brief":"写组织","content_boundary":"写部署","target_words":800}',
        )
        db.add(chapter)
        db.commit()

        from services.writer_service import build_context_bundle

        retrieval = type("R", (), {"chunks": [], "empty_reason": None})()
        with patch("services.chapter_context_service.retrieve_detailed", return_value=retrieval):
            bundle = build_context_bundle(db, project, chapter)

        assert bundle.get("evaluation_focus")
        assert "评标关注点" in bundle["evaluation_focus"]
    finally:
        db.close()


def test_compact_writing_guide_extracts_bullets():
    from prompts.writer_prompt import compact_writing_guide

    excerpt = compact_writing_guide("电力工程", max_chars=600)
    assert excerpt
    assert "参数" in excerpt or "施工" in excerpt
    assert len(excerpt) <= 600


def test_writer_user_prompt_includes_guide_excerpt_for_construction(monkeypatch):
    from prompts.writer_prompt import build_writer_user_prompt

    monkeypatch.setattr("config.WRITER_SYSTEM_COMPACT", True)
    prompt = build_writer_user_prompt(
        {
            "global_params": {},
            "requirements_text": "评分",
            "retrieval_text": "",
            "chapter_title": "GIS 安装调试",
            "chapter_level": 2,
            "chapter_path": "方案 > GIS",
            "guidance": {"brief": "写安装", "content_boundary": "写工序", "target_words": 800},
            "engineering_domain": "电力工程",
            "writing_guide_excerpt": "- 专项施工方案：工序流程、关键控制点",
            "sibling_leaf_titles": [],
            "other_leaf_titles": [],
        }
    )
    assert "领域写作要点" in prompt
    assert "工序流程" in prompt


def test_maybe_refine_evaluation_focus_skipped_by_default(monkeypatch):
    from services.requirement_prompt import maybe_refine_evaluation_focus

    monkeypatch.setattr("config.EVALUATION_FOCUS_LLM_REFINE", False)
    base = "【本章评标关注点】\n- [10分] GIS：关键词：GIS"
    assert maybe_refine_evaluation_focus(base, {"chapter_title": "GIS 安装", "requirements": []}) == base


def test_maybe_refine_evaluation_focus_calls_llm_when_enabled(monkeypatch):
    from types import SimpleNamespace

    from services.requirement_prompt import maybe_refine_evaluation_focus

    monkeypatch.setattr("config.EVALUATION_FOCUS_LLM_REFINE", True)
    monkeypatch.setattr("config.EVALUATION_FOCUS_REFINE_MIN_SCORE", 8.0)
    monkeypatch.setattr(
        "llm.llm_client.call_llm_text",
        lambda *_a, **_k: "- 写 GIS 就位工序\n- 含交接试验记录",
    )
    base = "【本章评标关注点】\n- [12分] GIS 安装"
    req = SimpleNamespace(score_value=12)
    out = maybe_refine_evaluation_focus(
        base,
        {"chapter_title": "GIS 安装", "requirements": [req]},
    )
    assert "就位工序" in out

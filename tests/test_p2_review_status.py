"""P2：红黄绿状态、软质检分段、评分覆盖回写。"""

import json
import sys
import uuid
from unittest.mock import MagicMock, patch

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from prompts.qa_prompt import sample_content_windows_for_qa, build_qa_user_prompt
from services.response_matrix_service import (
    apply_matrix_coverage_to_leaves,
    matrix_issues_for_chapter,
)
from services.writer_service import run_soft_qa, write_and_qa_chapter


def test_sample_content_windows_short_single():
    text = "短正文" * 20
    windows = sample_content_windows_for_qa(text, threshold=8000)
    assert len(windows) == 1
    assert windows[0][0] == "全文"


def test_sample_content_windows_long_three():
    text = "A" * 3000 + "M" * 3000 + "Z" * 3000
    windows = sample_content_windows_for_qa(text, threshold=8000, window=2800)
    assert len(windows) == 3
    labels = [w[0] for w in windows]
    assert labels == ["开头", "中段", "结尾"]
    assert windows[0][1].startswith("A")
    assert windows[2][1].endswith("Z")


def test_build_qa_user_prompt_segment_label():
    prompt = build_qa_user_prompt(
        "片段正文",
        {
            "chapter_title": "施工方案",
            "chapter_path": "方案 > 施工",
            "requirements_text": "评分",
            "retrieval_text": "",
            "sibling_leaf_titles": [],
            "other_leaf_titles": [],
        },
        segment_label="中段",
    )
    assert "抽检片段标签：【中段】" in prompt
    assert "片段正文" in prompt


def test_run_soft_qa_merges_segment_issues(monkeypatch):
    calls = {"n": 0}

    def fake_once(content, bundle, *, segment_label=None):
        calls["n"] += 1
        if segment_label == "中段":
            return {
                "passed": False,
                "coverage_issues": ["中段缺关键词"],
                "faithfulness_issues": [],
                "scope_issues": [],
            }
        return {
            "passed": True,
            "coverage_issues": [],
            "faithfulness_issues": [],
            "scope_issues": [],
        }

    monkeypatch.setattr("services.chapter_qa_orchestrator._run_soft_qa_once", fake_once)
    monkeypatch.setattr(
        "services.chapter_qa_orchestrator.sample_content_windows_for_qa",
        lambda _c: [("开头", "a"), ("中段", "b"), ("结尾", "c")],
    )
    result = run_soft_qa("x" * 9000, {"chapter_title": "t"})
    assert result["passed"] is False
    assert any("中段" in x for x in result["coverage_issues"])
    assert calls["n"] == 3


def test_matrix_issues_for_chapter_missing_keyword():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="矩阵单章", status="done")
        db.add(project)
        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="GIS 安装调试",
            keyword="GIS,交接试验",
            mandatory_elements="交接试验",
            status="confirmed",
        )
        db.add(req)
        chapter = TechOutline(
            id=str(uuid.uuid4()),
            project_id=pid,
            title="安装方案",
            is_leaf=1,
            sort_order=1,
            level=2,
            requirement_ids=json.dumps([req.id]),
            generated_content="本章仅描述一般安装流程，未涉及专项试验。",
            review_status="green",
        )
        db.add(chapter)
        db.commit()

        issues = matrix_issues_for_chapter(db, project, chapter)
        assert issues
        assert any("必备要素" in x or "关键词" in x for x in issues)

        changed = apply_matrix_coverage_to_leaves(db, project, [chapter])
        db.commit()
        db.refresh(chapter)
        assert changed == 1
        assert chapter.review_status == "yellow"
        assert "必备要素" in (chapter.review_errors or "") or "关键词" in (chapter.review_errors or "")
    finally:
        db.close()


def test_matrix_issues_for_chapter_combines_sibling_coverage():
    """同一评分项绑定多章时，按合并正文判覆盖，单章缺项不应误报。"""
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="矩阵多章", status="done")
        db.add(project)
        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="安全文明施工",
            keyword="安全,文明",
            mandatory_elements="安全措施,文明施工",
            is_risk_item=1,
            status="confirmed",
        )
        db.add(req)
        rid = json.dumps([req.id])
        ch_a = TechOutline(
            id=str(uuid.uuid4()),
            project_id=pid,
            title="安全措施",
            is_leaf=1,
            sort_order=1,
            level=2,
            requirement_ids=rid,
            generated_content="本章落实安全措施与隐患排查，设置专职安全员。",
            review_status="green",
        )
        ch_b = TechOutline(
            id=str(uuid.uuid4()),
            project_id=pid,
            title="文明施工",
            is_leaf=1,
            sort_order=2,
            level=2,
            requirement_ids=rid,
            generated_content="本章落实文明施工与场容场貌管理，设置封闭围挡。",
            review_status="green",
        )
        db.add_all([ch_a, ch_b])
        db.commit()

        # 单章各自缺一项，合并后齐全
        assert not matrix_issues_for_chapter(db, project, ch_a)
        assert not matrix_issues_for_chapter(db, project, ch_b)
    finally:
        db.close()


def test_write_and_qa_exception_sets_red(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="异常红标", status="outline_locked")
        db.add(project)
        chapter = TechOutline(
            id=str(uuid.uuid4()),
            project_id=pid,
            title="施工组织",
            is_leaf=1,
            sort_order=1,
            level=1,
            requirement_ids="[]",
            review_status="generating",
            is_locked=1,
        )
        db.add(chapter)
        db.commit()

        monkeypatch.setattr("services.writer_service.ENABLE_CONTENT_PLAN", False)
        with patch(
            "services.writer_service.build_context_bundle",
            side_effect=RuntimeError("模拟崩溃"),
        ):
            try:
                write_and_qa_chapter(db, project, chapter)
                assert False, "应抛出异常"
            except RuntimeError:
                pass

        db.refresh(chapter)
        assert chapter.review_status == "red"
        assert "模拟崩溃" in (chapter.review_errors or "")
    finally:
        db.close()

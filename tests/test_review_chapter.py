"""章节重新验章测试。"""

import json
import uuid
from unittest.mock import patch

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.writer_service import review_chapter_content


def _seed_chapter(db, content: str, status: str = "yellow"):
    pid = str(uuid.uuid4())
    project = Project(
        id=pid,
        name="测试变电站",
        voltage_level="220kV",
        duration_days=180,
        status="done",
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
    chapter = TechOutline(
        id=str(uuid.uuid4()),
        project_id=pid,
        title="施工组织设计",
        sort_order=1,
        level=1,
        is_leaf=1,
        requirement_ids=f'["{req.id}"]',
        generated_content=content,
        review_status=status,
        review_errors=json.dumps(["旧问题"], ensure_ascii=False),
    )
    db.add(chapter)
    db.commit()
    return project, chapter


def test_review_chapter_content_sets_green_when_qa_passes():
    init_db()
    db = SessionLocal()
    try:
        content = (
            "本工程施工组织设计针对220kV变电站新建工程，总工期180日历天。"
            "施工组织方案包括人员配置12人、机械投入3台、关键工序质量控制点15处。"
            "完全响应招标文件施工组织设计要求。"
        )
        project, chapter = _seed_chapter(db, content)
        with patch("services.chapter_qa_orchestrator.run_soft_qa", return_value={"passed": True}), patch(
            "services.chapter_qa_orchestrator.generate_summary", return_value="摘要"
        ):
            result = review_chapter_content(db, project, chapter, refresh_summary=False)
        assert result.review_status == "green"
        assert result.review_errors is None
    finally:
        db.close()


def test_review_chapter_content_sets_yellow_when_soft_qa_skipped():
    init_db()
    db = SessionLocal()
    try:
        content = (
            "本工程施工组织设计针对220kV变电站新建工程，总工期180日历天。"
            "施工组织方案包括人员配置12人、机械投入3台、关键工序质量控制点15处。"
            "完全响应招标文件施工组织设计要求。"
        )
        project, chapter = _seed_chapter(db, content)
        with patch(
            "services.chapter_qa_orchestrator.run_soft_qa",
            return_value={
                "passed": False,
                "skipped": True,
                "skip_reason": "network timeout",
            },
        ), patch("services.chapter_qa_orchestrator.generate_summary", return_value="摘要"):
            result = review_chapter_content(db, project, chapter, refresh_summary=False)
        assert result.review_status == "yellow"
        errors = json.loads(result.review_errors)
        assert any("软质检未执行" in e for e in errors)
    finally:
        db.close()


def test_review_chapter_content_keeps_yellow_when_hard_qa_fails():
    init_db()
    db = SessionLocal()
    try:
        project, chapter = _seed_chapter(db, "本章方案 TODO 待补充，包含模板残留。")
        result = review_chapter_content(db, project, chapter, refresh_summary=False)
        assert result.review_status == "yellow"
        errors = json.loads(result.review_errors)
        assert any("模板残留" in e or "TODO" in e for e in errors)
    finally:
        db.close()


def test_review_chapter_content_normalizes_paste_spacing():
    """重新验章前清洗全角/连续空格，并写回正文，避免粘贴排版残留硬拦。"""
    init_db()
    db = SessionLocal()
    try:
        content = (
            "　　本工程施工组织设计针对220kV变电站新建工程，总工期180日历天。"
            "施工组织方案包括人员配置12人、机械投入3台、关键工序质量控制点15处。"
            "完全响应招标文件施工组织设计要求。"
        )
        project, chapter = _seed_chapter(db, content)
        with patch("services.chapter_qa_orchestrator.run_soft_qa", return_value={"passed": True}), patch(
            "services.chapter_qa_orchestrator.generate_summary", return_value="摘要"
        ):
            result = review_chapter_content(db, project, chapter, refresh_summary=False)
        assert "\u3000" not in (result.generated_content or "")
        assert "  " not in (result.generated_content or "")
        assert result.review_status == "green"
        assert result.review_errors is None
    finally:
        db.close()

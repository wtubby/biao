import json
import uuid

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.response_matrix_service import (
    apply_matrix_coverage_to_leaves,
    build_response_matrix,
    format_chapter_matrix_context,
)


def test_build_response_matrix_tracks_coverage_and_risk_gap():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="响应矩阵测试", status="done")
        db.add(project)

        covered_req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="GIS 安装调试方案",
            score_value=10,
            keyword="GIS,交接试验",
            mandatory_elements="GIS,交接试验",
            status="confirmed",
        )
        unbound_risk = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="安全文明刚性条款",
            score_value=5,
            keyword="安全文明",
            is_risk_item=1,
            status="confirmed",
        )
        db.add_all([covered_req, unbound_risk])

        chapter = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="GIS 安装调试",
            sort_order=1,
            level=2,
            is_leaf=1,
            requirement_ids=json.dumps([covered_req.id]),
            generated_content="本章编制 GIS 安装调试方案，包含交接试验记录与气室检查。",
            review_status="green",
        )
        db.add(chapter)
        db.commit()

        matrix = build_response_matrix(db, project)

        assert matrix["summary"]["covered"] == 1
        assert matrix["summary"]["unbound"] == 1
        assert matrix["summary"]["risk_uncovered"] == 1
        covered = next(row for row in matrix["rows"] if row["requirement_id"] == covered_req.id)
        assert covered["status"] == "covered"
        assert covered["bound_chapters"][0]["matched_keywords"]
    finally:
        db.close()


def test_format_chapter_matrix_context_lists_peers_and_summaries():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="矩阵上下文测试", status="done")
        db.add(project)

        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="施工组织设计",
            score_value=15,
            mandatory_elements="三级网络计划",
            status="confirmed",
        )
        db.add(req)

        current = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="施工部署",
            sort_order=2,
            level=2,
            is_leaf=1,
            requirement_ids=json.dumps([req.id]),
        )
        peer = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="施工准备",
            sort_order=1,
            level=2,
            is_leaf=1,
            requirement_ids=json.dumps([req.id]),
            last_summary="已说明临设布置与道路硬化。",
        )
        db.add_all([current, peer])
        db.commit()

        text = format_chapter_matrix_context(current, [req], [current, peer])
        assert "本章评分响应矩阵" in text
        assert "施工准备" in text
        assert "临设布置" in text
        assert "三级网络计划" in text
    finally:
        db.close()


def test_apply_matrix_coverage_marks_risk_gap_as_red():
    """刚性风险项未覆盖应打 red，不能只降为 yellow 后被 allow_yellow 带过。"""
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="刚性覆盖测试", status="done")
        db.add(project)

        risk_req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="安全文明刚性条款",
            score_value=5,
            keyword="安全文明施工",
            is_risk_item=1,
            status="confirmed",
        )
        normal_req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=pid,
            requirement_title="进度计划",
            score_value=8,
            keyword="横道图",
            is_risk_item=0,
            status="confirmed",
        )
        db.add_all([risk_req, normal_req])

        risk_chapter = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="安全管理",
            sort_order=1,
            level=2,
            is_leaf=1,
            requirement_ids=json.dumps([risk_req.id]),
            generated_content="本章说明现场管理组织与人员配置，未涉及相关刚性条款关键词。",
            review_status="green",
        )
        normal_chapter = TechOutline(
            project_id=pid,
            id=str(uuid.uuid4()),
            title="进度管理",
            sort_order=2,
            level=2,
            is_leaf=1,
            requirement_ids=json.dumps([normal_req.id]),
            generated_content="本章说明工期安排与资源配置，未写进度图表。",
            review_status="green",
        )
        db.add_all([risk_chapter, normal_chapter])
        db.commit()

        changed = apply_matrix_coverage_to_leaves(
            db, project, [risk_chapter, normal_chapter]
        )
        db.commit()

        assert changed == 2
        assert risk_chapter.review_status == "red"
        assert "刚性风险项" in (risk_chapter.review_errors or "")
        assert normal_chapter.review_status == "yellow"
        assert "刚性风险项" not in (normal_chapter.review_errors or "")
    finally:
        db.close()

import json
import uuid

from db.database import SessionLocal, init_db
from db.models import Project, TechRequirement
from services.outline_catalog_source import (
    CATALOG_SOURCE_REFERENCE,
    CATALOG_SOURCE_SCORE,
    apply_catalog_source,
    build_score_points_catalog_text,
    get_catalog_source,
    preview_catalog_source,
)
from services.tender_detail_service import set_tender_detail


def _req(title: str, **kwargs) -> TechRequirement:
    return TechRequirement(
        id=str(uuid.uuid4()),
        project_id="p1",
        requirement_title=title,
        score_value=kwargs.get("score_value", 5),
        status="confirmed",
    )


def test_build_score_points_catalog_text():
    reqs = [_req("施工组织设计"), _req("质量保证措施")]
    text = build_score_points_catalog_text(reqs)
    assert "（一）施工组织设计" in text
    assert "（二）质量保证措施" in text


def test_cn_index_beyond_ten():
    """中文序号须正确生成十一、十二等，不能按字符下标切片。"""
    titles = [f"评分项{i}" for i in range(1, 23)]
    reqs = [_req(t) for t in titles]
    text = build_score_points_catalog_text(reqs)
    lines = text.splitlines()
    expected = [
        "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
        "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九",
        "二十", "二十一", "二十二",
    ]
    for i, cn in enumerate(expected):
        assert lines[i] == f"（{cn}）评分项{i + 1}"


def test_apply_catalog_source_score_points():
    init_db()
    db = SessionLocal()
    pid = str(uuid.uuid4())
    try:
        project = Project(id=pid, status="planning")
        db.add(project)
        db.commit()

        reqs = [
            TechRequirement(
                id=str(uuid.uuid4()), project_id=pid, requirement_title="施工组织设计",
                score_value=10, status="confirmed",
            ),
            TechRequirement(
                id=str(uuid.uuid4()), project_id=pid, requirement_title="安全文明施工",
                score_value=8, status="confirmed",
            ),
        ]
        db.add_all(reqs)
        db.commit()

        result = apply_catalog_source(project, reqs, CATALOG_SOURCE_SCORE)
        db.commit()

        assert result["applied"] is True
        assert result["count"] == 2
        assert get_catalog_source(project) == CATALOG_SOURCE_SCORE
        meta = json.loads(project.extra_params)
        assert "施工组织设计" in meta["outline_catalog_text"]
    finally:
        db.close()


def test_apply_catalog_source_reference_format_from_extraction():
    init_db()
    db = SessionLocal()
    pid = str(uuid.uuid4())
    try:
        project = Project(id=pid, status="planning")
        db.add(project)
        db.commit()

        set_tender_detail(project, {
            "bid_reference_catalog": "（一）工程概况\n（二）施工组织设计\n  1. 施工部署",
        })
        db.commit()

        result = apply_catalog_source(project, [], CATALOG_SOURCE_REFERENCE)
        db.commit()

        assert result["applied"] is True
        assert result["count"] >= 2
        assert get_catalog_source(project) == CATALOG_SOURCE_REFERENCE
    finally:
        db.close()


def test_preview_score_points_allows_single_requirement():
    """招标文件常只有 1 个大方案评分项，应允许按评分点生成目录。"""
    project = Project(id="p3", extra_params="{}")
    preview = preview_catalog_source(project, [_req("技术方案")], CATALOG_SOURCE_SCORE)
    assert preview["available"] is True
    assert preview["count"] >= 1
    assert "技术方案" in preview["text"]


def test_preview_score_points_empty_suggests_reference_or_manual():
    """无评分项时不阻断流程，提示改用参考格式或手写目录。"""
    project = Project(id="p4", extra_params="{}")
    preview = preview_catalog_source(project, [], CATALOG_SOURCE_SCORE)
    assert preview["available"] is False
    assert "参考" in (preview["hint"] or "") or "手动" in (preview["hint"] or "")


def test_preview_reference_empty_still_switchable_hint():
    """无本标书参考目录时 preview.available=False，但前端仍应允许切换到手写。"""
    project = Project(id="p5", extra_params="{}")
    preview = preview_catalog_source(project, [], CATALOG_SOURCE_REFERENCE)
    assert preview["available"] is False
    hint = preview["hint"] or ""
    assert "本标书" in hint
    assert "粘贴" in hint or "核对" in hint


def test_preview_reference_available_only_from_bid_extraction():
    """有手写目录但无本标书提取时，仍视为不可自动应用参考格式。"""
    project = Project(
        id="p6",
        extra_params=json.dumps({
            "outline_catalog_text": "（一）工程概况\n（二）施工组织设计",
            "outline_catalog": [
                {"title": "工程概况", "children": []},
                {"title": "施工组织设计", "children": []},
            ],
        }, ensure_ascii=False),
    )
    preview = preview_catalog_source(project, [], CATALOG_SOURCE_REFERENCE)
    assert preview["available"] is False
    assert "本标书" in (preview["hint"] or "")


def test_apply_reference_unparseable_still_fills_text():
    """参考原文编号不规范时仍填入文本，便于人工编辑。"""
    init_db()
    db = SessionLocal()
    pid = str(uuid.uuid4())
    try:
        project = Project(id=pid, status="planning")
        db.add(project)
        db.commit()

        set_tender_detail(project, {
            "bid_reference_catalog": "工程概况\n施工组织设计\n质量保证",
        })
        db.commit()

        result = apply_catalog_source(project, [], CATALOG_SOURCE_REFERENCE)
        assert result["applied"] is False
        assert "工程概况" in result["text"]
        assert get_catalog_source(project) == CATALOG_SOURCE_REFERENCE
    finally:
        db.close()

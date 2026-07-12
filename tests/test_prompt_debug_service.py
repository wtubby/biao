"""提示词预览服务单元测试。"""

import json
import sys
import uuid
from unittest.mock import MagicMock, patch

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline
from services.catalog_parser import parse_catalog_text
from services.project_meta import set_meta, set_outline_catalog
from services.prompt_debug_service import (
    _first_branch_from_catalog,
    build_chapter_prompt_preview,
    build_outline_prompt_preview,
)


def test_first_branch_from_catalog_level2():
    catalog = parse_catalog_text(
        "（一）工程概况\n  1. 项目特点\n（二）施工组织设计\n  1. 施工部署"
    )
    branch = _first_branch_from_catalog(catalog)
    assert branch is not None
    assert branch["title"] == "项目特点"
    assert branch["level"] == 2
    assert branch["id"].endswith(".1")


def test_outline_prompt_preview_uses_outline_level2_branch():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="预览测试工程",
            voltage_level="220kV",
            duration_days=180,
            location="成都",
            status="outline_locked",
        )
        db.add(project)
        set_meta(project, project_type="变电站新建", engineering_domain="电力工程")
        catalog_text = "（一）工程概况\n（二）施工组织设计"
        set_outline_catalog(project, catalog_text, parse_catalog_text(catalog_text))

        db.add(
            TechOutline(
                id="1",
                project_id=pid,
                title="工程概况",
                level=1,
                sort_order=1,
                is_leaf=0,
            )
        )
        db.add(
            TechOutline(
                id="2",
                project_id=pid,
                title="施工组织设计",
                parent_id=None,
                level=1,
                sort_order=2,
                is_leaf=0,
            )
        )
        db.add(
            TechOutline(
                id="2.1",
                project_id=pid,
                title="施工部署",
                parent_id="2",
                level=2,
                sort_order=3,
                is_leaf=0,
            )
        )
        db.commit()

        preview = build_outline_prompt_preview(db, project)
        branch_stage = next(s for s in preview["stages"] if s["id"] == "outline_branch")
        assert "施工部署" in branch_stage["user"]
        assert "（示例二级分支）" not in branch_stage["user"]
        assert preview["preview_branch"]["title"] == "施工部署"
    finally:
        db.close()


def test_chapter_prompt_preview_includes_content_plan_in_writer():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="章节预览测试",
            voltage_level="220kV",
            duration_days=180,
            location="成都",
            status="outline_locked",
        )
        db.add(project)
        set_meta(project, engineering_domain="电力工程")
        plan = {
            "key_points": ["里程碑节点", "关键路径"],
            "technical_methods": ["三级网络计划"],
            "data_to_include": ["总工期180天"],
            "charts_needed": [{"type": "GANTT_DATA", "purpose": "总体进度"}],
            "word_count_target": 1200,
            "avoid": ["主变吊装工艺"],
        }
        chapter = TechOutline(
            id="c1",
            project_id=pid,
            title="施工进度计划",
            level=2,
            sort_order=1,
            is_leaf=1,
            requirement_ids="[]",
            writing_guidance=json.dumps(
                {
                    "brief": "写进度",
                    "content_boundary": "只写进度",
                    "target_words": 1200,
                },
                ensure_ascii=False,
            ),
            content_plan=json.dumps(plan, ensure_ascii=False),
        )
        db.add(chapter)
        db.commit()

        retrieval = type(
            "R",
            (),
            {"chunks": [], "empty_reason": None},
        )()
        with patch(
            "services.chapter_context_service.retrieve_detailed",
            return_value=retrieval,
        ):
            preview = build_chapter_prompt_preview(db, project, chapter)

        writer_stage = next(s for s in preview["stages"] if s["id"] == "writer")
        qa_stage = next(s for s in preview["stages"] if s["id"] == "qa")
        assert "本章写作规划" in writer_stage["user"]
        assert "里程碑节点" in writer_stage["user"]
        assert "写作规划必须覆盖要点" in qa_stage["user"]
        assert "关键路径" in qa_stage["user"]
        assert preview.get("prompt_metrics", {}).get("total_tokens_est", 0) > 0
        assert writer_stage.get("metrics", {}).get("user_tokens_est", 0) > 0
    finally:
        db.close()

"""评分项提示词格式化单元测试。"""

import sys
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from prompts.plan_prompt import build_plan_user_prompt
from prompts.writer_prompt import build_writer_user_prompt
from services.requirement_prompt import (
    format_requirement_block,
    format_requirements_text,
    requirements_response_hint,
)
from services.writer_service import build_context_bundle


def _req(**kwargs):
    base = dict(
        id="r1",
        project_id="p1",
        requirement_title="施工组织设计",
        score_value=15.0,
        is_risk_item=1,
        keyword="施工组织,总体部署",
        mandatory_elements="三级网络计划、周报制度",
        source_text="施工组织设计应包括总体部署、进度安排及资源配置。",
        score_category="技术",
        status="confirmed",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_format_requirement_block_includes_score_mandatory_and_risk():
    text = format_requirement_block(_req())
    assert "分值：15 分" in text
    assert "刚性：是" in text
    assert "必备要素" in text
    assert "三级网络计划" in text
    assert "评分关键词" in text
    assert "高分项" in text
    assert "评分细则" in text


def test_requirements_response_hint_mentions_total_and_mandatory():
    hint = requirements_response_hint([_req(), _req(requirement_title="质量管理", score_value=5)])
    assert "响应要求" in hint
    assert "20 分" in hint
    assert "必备要素" in hint
    assert "刚性" in hint


def test_build_context_bundle_structured_requirements_text():
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
            is_risk_item=1,
            keyword="施工组织",
            mandatory_elements="三级网络计划",
            source_text="应编制施工组织设计。",
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

        retrieval = type("R", (), {"chunks": [], "empty_reason": None})()
        with patch("services.chapter_context_service.retrieve_detailed", return_value=retrieval):
            bundle = build_context_bundle(db, project, chapter)

        assert "分值：12 分" in bundle["requirements_text"]
        assert "必备要素" in bundle["requirements_text"]
        assert "三级网络计划" in bundle["requirements_text"]
        assert bundle.get("requirements_hint")
        assert "响应要求" in bundle["requirements_hint"]

        writer = build_writer_user_prompt(bundle)
        plan = build_plan_user_prompt(bundle)
        assert "三级网络计划" in writer
        assert "响应要求" in writer
        assert "必备要素" in plan
        assert "必备要素" in plan
    finally:
        db.close()

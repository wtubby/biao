"""提示词用全局工程信息单元测试。"""

import sys
import uuid
from unittest.mock import MagicMock, patch

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline
from services.outline_service import _global_engineering_info, _validate_global_info
from services.project_meta import set_meta
from services.prompt_project_info import build_prompt_global_params
from services.writer_service import build_context_bundle


def test_build_prompt_global_params_uses_chinese_keys():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="测试工程",
            voltage_level="220kV",
            capacity="2×180MVA",
            duration_days=180,
            location="成都",
        )
        db.add(project)
        set_meta(
            project,
            project_type="变电站新建",
            engineering_domain="电力工程",
            contract_mode="EPC",
            extra_notes="场区狭小",
        )
        db.commit()

        params = build_prompt_global_params(project)
        assert params["工程名称"] == "测试工程"
        assert params["项目类型"] == "变电站新建"
        assert params["工程规模"] == "2×180MVA"
        assert params["总工期"] == 180
        assert params["承包方式"] == "EPC"
        assert params["补充说明"] == "场区狭小"

        outline_info = _global_engineering_info(project)
        assert outline_info == params
    finally:
        db.close()


def test_outline_and_writer_share_same_global_params():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="统一字段测试",
            voltage_level="220kV",
            duration_days=120,
            location="绵阳",
        )
        db.add(project)
        set_meta(project, project_type="线路工程", engineering_domain="电力工程")
        chapter = TechOutline(
            id="c1",
            project_id=pid,
            title="施工组织设计",
            is_leaf=1,
            sort_order=1,
        )
        db.add(chapter)
        db.commit()

        outline_info = _global_engineering_info(project)
        with patch(
            "services.chapter_context_service.retrieve_detailed",
            return_value=type("R", (), {"chunks": [], "empty_reason": None})(),
        ):
            bundle = build_context_bundle(db, project, chapter)
        assert bundle["global_params"] == outline_info
    finally:
        db.close()


def test_validate_global_info_accepts_chinese_keys():
    _validate_global_info(
        {
            "工程名称": "测",
            "项目类型": "变电站新建",
            "电压等级": "220kV",
            "建设地点": "成都",
            "总工期": 180,
            "工程领域": "电力工程",
        }
    )

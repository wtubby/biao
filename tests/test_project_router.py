"""项目路由：全局工程信息保存后标记手动确认字段，并同步 notice。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from db.models import Project
from routers.project import GlobalParamsUpdate, update_global_params
from services.project_meta import get_meta
from services.tender_detail_service import get_tender_detail, set_tender_detail


def test_update_global_params_marks_fields_manually_confirmed():
    project = Project(
        id="p1",
        name="初始工程名",
        status="confirming",
        created_at=datetime(2026, 1, 1),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project

    body = GlobalParamsUpdate(
        name="用户确认的工程名",
        project_type="电缆工程",
        engineering_domain="电力工程",
        contract_mode="EPC",
        voltage_level="10kV",
        location="宜宾市",
        duration_days=60,
        capacity="100MVA",
        target_pages=80,
    )
    with patch("routers.project.sync_basic_info_fact"):
        out = update_global_params("p1", body, db=db)

    assert out.name == "用户确认的工程名"
    confirmed = set(get_meta(project).get("manually_confirmed_fields") or [])
    assert "name" in confirmed
    assert "voltage_level" in confirmed
    assert "capacity" in confirmed
    assert "location" in confirmed
    assert "duration_days" in confirmed
    assert "project_type" in confirmed
    assert "contract_mode" in confirmed
    assert "engineering_domain" in confirmed
    assert "budget_yuan" in confirmed
    assert "target_pages" in confirmed
    db.commit.assert_called()


def test_update_global_params_syncs_notice_fields():
    """全局工程信息保存后，招标详情 notice 对应字段也要更新，避免两表单打架。"""
    project = Project(
        id="p2",
        name="旧工程名",
        status="confirming",
        created_at=datetime(2026, 1, 1),
    )
    set_tender_detail(project, {
        "notice": {
            "project_name": "解析出来的旧工程名",
            "voltage_level": "35kV",
            "agency": "某招标代理",
        },
    })
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project

    body = GlobalParamsUpdate(
        name="用户确认的工程名",
        project_type="电缆工程",
        engineering_domain="电力工程",
        contract_mode="EPC",
        voltage_level="10kV",
        location="宜宾市",
        duration_days=90,
        capacity="50MVA",
        target_pages=100,
        extra_notes="补充说明",
    )
    with patch("routers.project.sync_basic_info_fact"):
        update_global_params("p2", body, db=db)

    notice = get_tender_detail(project)["notice"]
    assert notice["project_name"] == "用户确认的工程名"
    assert notice["voltage_level"] == "10kV"
    assert notice["capacity"] == "50MVA"
    assert notice["location"] == "宜宾市"
    assert notice["duration_text"] == "90个日历天"
    assert notice["project_type"] == "电缆工程"
    assert notice["contract_mode"] == "EPC"
    assert notice["bid_domain"] == "电力工程"
    assert notice["target_pages"] == 100
    assert notice["overview"] == "补充说明"
    # 非共享字段应保留
    assert notice["agency"] == "某招标代理"
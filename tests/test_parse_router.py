"""parse 路由：招标详情 PATCH 仅标记实际修改的 notice 字段。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from db.models import Project
from routers.parse import TenderDetailUpdate, TenderNoticeUpdate, update_project_tender_detail
from services.project_meta import get_meta
from services.tender_detail_service import get_tender_detail, set_tender_detail


def _mock_db(project: Project) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project
    return db


def test_tender_detail_patch_blind_bid_only_does_not_lock_other_fields():
    project = Project(id="p-blind", name="解析工程名", status="confirming", created_at=datetime(2026, 1, 1))
    set_tender_detail(project, {"notice": {"voltage_level": "10kV", "blind_bid": None}})

    body = TenderDetailUpdate(notice=TenderNoticeUpdate(blind_bid=True))
    update_project_tender_detail("p-blind", body, db=_mock_db(project))

    assert get_tender_detail(project)["notice"]["blind_bid"] is True
    assert get_meta(project).get("manually_confirmed_fields") in (None, [])


def test_tender_detail_patch_notice_marks_only_touched_protectable_fields():
    project = Project(id="p-notice", name="旧名", status="confirming", created_at=datetime(2026, 1, 1))
    set_tender_detail(project, {"notice": {"voltage_level": "35kV"}})

    body = TenderDetailUpdate(
        notice=TenderNoticeUpdate(voltage_level="10kV", blind_bid=False),
    )
    with patch("routers.parse.apply_notice_to_project"):
        update_project_tender_detail("p-notice", body, db=_mock_db(project))

    confirmed = set(get_meta(project).get("manually_confirmed_fields") or [])
    assert confirmed == {"voltage_level"}


def test_tender_detail_patch_full_form_only_locks_changed_fields():
    """前端若提交全部表单字段，未改动的值不得打上手动确认标记。"""
    project = Project(id="p-full", name="电缆工程", status="confirming", created_at=datetime(2026, 1, 1))
    set_tender_detail(project, {
        "notice": {
            "project_name": "电缆工程",
            "voltage_level": "10kV",
            "location": "成都",
            "duration_text": "60个日历天",
            "bid_domain": "电力工程",
        },
    })

    body = TenderDetailUpdate(
        notice=TenderNoticeUpdate(
            project_name="电缆工程",
            voltage_level="35kV",
            location="成都",
            duration_text="60个日历天",
            bid_domain="电力工程",
            blind_bid=False,
        ),
    )
    with patch("routers.parse.apply_notice_to_project"):
        update_project_tender_detail("p-full", body, db=_mock_db(project))

    confirmed = set(get_meta(project).get("manually_confirmed_fields") or [])
    assert confirmed == {"voltage_level"}

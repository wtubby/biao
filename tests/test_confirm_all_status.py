"""confirm-all 不得把已锁定项目回退为 planning。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from db.models import Project, TechRequirement
from routers.parse import confirm_all_requirements


def _project(status: str) -> Project:
    return Project(
        id="p-confirm",
        name="测试工程",
        status=status,
        created_at=datetime(2026, 1, 1),
        voltage_level="220kV",
        location="某市",
        duration_days=180,
    )


def test_confirm_all_does_not_regress_outline_locked():
    project = _project("outline_locked")
    db = MagicMock()

    def query_side_effect(model):
        q = MagicMock()
        if model is Project:
            q.filter.return_value.first.return_value = project
            return q
        if model is TechRequirement:
            q.filter.return_value.all.return_value = []
            return q
        q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect

    with (
        patch("routers.parse.get_meta", return_value={"project_type": "线路"}),
        patch("routers.parse.get_tender_detail", return_value={"notice": {}}),
    ):
        result = confirm_all_requirements("p-confirm", db)

    assert result["status"] == "outline_locked"
    assert project.status == "outline_locked"


def test_confirm_all_sets_planning_from_confirming():
    project = _project("confirming")
    db = MagicMock()

    def query_side_effect(model):
        q = MagicMock()
        if model is Project:
            q.filter.return_value.first.return_value = project
            return q
        if model is TechRequirement:
            q.filter.return_value.all.return_value = []
            return q
        q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect

    with (
        patch("routers.parse.get_meta", return_value={"project_type": "线路"}),
        patch("routers.parse.get_tender_detail", return_value={"notice": {}}),
    ):
        result = confirm_all_requirements("p-confirm", db)

    assert result["status"] == "planning"
    assert project.status == "planning"

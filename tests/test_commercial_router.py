"""商务标路由：项目校验与章节编辑不应抛未定义异常。"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from db.models import Project
from routers.commercial import (
    SectionUpdateBody,
    patch_commercial_section,
)


def _mock_db_with_project(project: Project | None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project
    return db


def test_patch_commercial_section_calls_update_when_project_exists(monkeypatch):
    project = Project(id="p1", name="测试工程", bid_scope="technical_commercial")
    db = _mock_db_with_project(project)

    fake_row = MagicMock()
    fake_row.id = "sec1"

    captured = {}

    def fake_update(db_arg, project_id, section_id, **kwargs):
        captured["project_id"] = project_id
        captured["section_id"] = section_id
        captured["kwargs"] = kwargs
        return fake_row

    monkeypatch.setattr(
        "routers.commercial.update_commercial_section", fake_update
    )
    monkeypatch.setattr(
        "routers.commercial.section_to_dict", lambda row: {"id": row.id}
    )

    body = SectionUpdateBody(content_markdown="## 已确认\n\n核对完成。")
    result = patch_commercial_section("p1", "sec1", body, db=db)

    assert result["success"] is True
    assert captured["project_id"] == "p1"
    assert captured["section_id"] == "sec1"
    db.commit.assert_called_once()


def test_patch_commercial_section_404_when_project_missing():
    db = _mock_db_with_project(None)
    body = SectionUpdateBody(content_markdown="内容")

    with pytest.raises(HTTPException) as exc_info:
        patch_commercial_section("missing", "sec1", body, db=db)

    assert exc_info.value.status_code == 404


def test_patch_commercial_section_400_on_value_error(monkeypatch):
    project = Project(id="p1", name="测试工程", bid_scope="technical_commercial")
    db = _mock_db_with_project(project)

    def fake_update(*args, **kwargs):
        raise ValueError("章节不存在")

    monkeypatch.setattr(
        "routers.commercial.update_commercial_section", fake_update
    )

    body = SectionUpdateBody(content_markdown="内容")
    with pytest.raises(HTTPException) as exc_info:
        patch_commercial_section("p1", "sec1", body, db=db)

    assert exc_info.value.status_code == 400

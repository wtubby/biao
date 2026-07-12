"""生成启动互斥：generating 状态不可重复启动。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from db.models import Project, TechOutline
from routers.generate import resume_generate, start_generate


def _project(status: str = "outline_locked") -> Project:
    return Project(
        id="p-gen",
        name="测试工程",
        status=status,
        created_at=datetime(2026, 1, 1),
        pause_requested=0,
    )


def _db_with_project(project: Project, locked: bool = True):
    db = MagicMock()
    outline_q = MagicMock()
    outline_q.filter.return_value.first.return_value = (
        TechOutline(id="c1", project_id=project.id, is_locked=1) if locked else None
    )

    def query_side_effect(model):
        q = MagicMock()
        if model is Project:
            q.filter.return_value.first.return_value = project
            return q
        if model is TechOutline:
            return outline_q
        q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect
    return db


def test_start_generate_rejects_when_already_generating():
    project = _project("generating")
    db = _db_with_project(project)

    with patch("routers.generate._require_format_confirmed"):
        with pytest.raises(HTTPException) as exc:
            start_generate("p-gen", db)

    assert exc.value.status_code == 409


def test_start_generate_claims_slot_before_background_task():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.reset_queue"),
        patch("routers.generate.spawn_async") as spawn,
        patch("routers.generate._require_format_confirmed"),
    ):
        result = start_generate("p-gen", db)

    assert result["success"] is True
    assert project.status == "generating"
    db.commit.assert_called()
    spawn.assert_called_once()


def test_start_generate_rejects_without_format_confirm():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.spawn_async") as spawn,
        patch(
            "services.generation_config.get_generation_config",
            return_value={"format_confirmed_at": None},
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            start_generate("p-gen", db)

    assert exc.value.status_code == 400
    spawn.assert_not_called()


def test_resume_generate_rejects_when_already_generating():
    project = _project("generating")
    db = _db_with_project(project)

    with patch("routers.generate._require_format_confirmed"):
        with pytest.raises(HTTPException) as exc:
            resume_generate("p-gen", db)

    assert exc.value.status_code == 409


def test_resume_generate_requires_format_confirm():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.spawn_async") as spawn,
        patch(
            "services.generation_config.get_generation_config",
            return_value={"format_confirmed_at": None},
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            resume_generate("p-gen", db)

    assert exc.value.status_code == 400
    spawn.assert_not_called()


def test_resume_generate_spawns_async_job():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.reset_queue"),
        patch("routers.generate.spawn_async") as spawn,
        patch("routers.generate._require_format_confirmed"),
    ):
        result = resume_generate("p-gen", db)

    assert result["success"] is True
    assert project.status == "generating"
    spawn.assert_called_once()

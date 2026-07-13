"""生成启动互斥：generating 状态不可重复启动；崩溃残留可接管。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from db.models import Project, TechOutline
from routers.generate import (
    _claim_generation_slot,
    generate_chapter,
    regenerate_chapter,
    resume_generate,
    start_generate,
)
from services.generation_service import generate_single_chapter


def _project(status: str = "outline_locked") -> Project:
    return Project(
        id="p-gen",
        name="测试工程",
        status=status,
        created_at=datetime(2026, 1, 1),
        pause_requested=0,
    )


def _db_with_project(project: Project, locked: bool = True, *, update_rows: int | None = None):
    db = MagicMock()
    outline_q = MagicMock()
    outline_q.filter.return_value.first.return_value = (
        TechOutline(id="c1", project_id=project.id, is_locked=1) if locked else None
    )

    def query_side_effect(model):
        q = MagicMock()
        if model is Project:
            filtered = q.filter.return_value
            filtered.first.return_value = project
            if update_rows is not None:
                filtered.update.return_value = update_rows
            else:
                filtered.update.return_value = 0 if project.status == "generating" else 1
            return q
        if model is TechOutline:
            return outline_q
        q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect
    return db


def test_start_generate_rejects_when_job_already_running():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.try_acquire_job", return_value=False),
        patch("routers.generate._require_format_confirmed"),
    ):
        with pytest.raises(HTTPException) as exc:
            start_generate("p-gen", db)

    assert exc.value.status_code == 409


def test_claim_generation_slot_uses_conditional_update():
    """条件 UPDATE 抢占失败（受影响行数 0）时应 409，并释放进程内槽位。"""
    project = _project("outline_locked")
    db = _db_with_project(project, update_rows=0)

    with (
        patch("routers.generate.try_acquire_job", return_value=True) as acquire,
        patch("routers.generate.release_job") as release,
    ):
        with pytest.raises(HTTPException) as exc:
            _claim_generation_slot(project, db, "启动内容生成")

    assert exc.value.status_code == 409
    acquire.assert_called_once_with("generate:p-gen")
    release.assert_called_once_with("generate:p-gen")
    db.rollback.assert_called()
    db.commit.assert_not_called()


def test_claim_generation_slot_atomic_success():
    project = _project("outline_locked")
    db = MagicMock()
    filtered = MagicMock()
    filtered.update.return_value = 1
    q = MagicMock()
    q.filter.return_value = filtered
    db.query.return_value = q

    with (
        patch("routers.generate.try_acquire_job", return_value=True),
        patch("routers.generate.release_job") as release,
    ):
        job_key = _claim_generation_slot(project, db, "启动内容生成")

    assert job_key == "generate:p-gen"
    assert project.status == "generating"
    assert project.pause_requested == 0
    db.commit.assert_called()
    release.assert_not_called()
    filtered.update.assert_called_once_with(
        {"status": "generating", "pause_requested": 0},
        synchronize_session=False,
    )


def test_claim_reclaims_orphaned_generating_slot():
    """DB 为 generating 但进程内无任务时，应接管残留槽位而非 409。"""
    project = _project("generating")
    db = MagicMock()
    filtered = MagicMock()
    filtered.update.return_value = 1
    q = MagicMock()
    q.filter.return_value = filtered
    db.query.return_value = q

    with (
        patch("routers.generate.try_acquire_job", return_value=True),
        patch("routers.generate.release_job") as release,
    ):
        job_key = _claim_generation_slot(project, db, "启动内容生成")

    assert job_key == "generate:p-gen"
    assert project.status == "generating"
    release.assert_not_called()
    filtered.update.assert_called_once()


def test_start_generate_claims_slot_before_background_task():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.try_acquire_job", return_value=True),
        patch("routers.generate.release_job"),
        patch("routers.generate.reset_queue"),
        patch("routers.generate.spawn_async", return_value=True) as spawn,
        patch("routers.generate._require_format_confirmed"),
    ):
        result = start_generate("p-gen", db)

    assert result["success"] is True
    assert project.status == "generating"
    db.commit.assert_called()
    spawn.assert_called_once()
    assert spawn.call_args.kwargs.get("dedupe_key") == "generate:p-gen"
    assert spawn.call_args.kwargs.get("already_acquired") is True


def test_start_generate_rejects_when_spawn_dedupe_fails():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.try_acquire_job", return_value=True),
        patch("routers.generate.release_job") as release,
        patch("routers.generate.reset_queue"),
        patch("routers.generate.spawn_async", return_value=False),
        patch("routers.generate._require_format_confirmed"),
    ):
        with pytest.raises(HTTPException) as exc:
            start_generate("p-gen", db)

    assert exc.value.status_code == 409
    release.assert_called_with("generate:p-gen")


def test_start_generate_rejects_without_format_confirm():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.spawn_async", return_value=True) as spawn,
        patch(
            "services.generation_config.get_generation_config",
            return_value={"format_confirmed_at": None},
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            start_generate("p-gen", db)

    assert exc.value.status_code == 400
    spawn.assert_not_called()


def test_resume_generate_rejects_when_job_already_running():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.try_acquire_job", return_value=False),
        patch("routers.generate._require_format_confirmed"),
    ):
        with pytest.raises(HTTPException) as exc:
            resume_generate("p-gen", db)

    assert exc.value.status_code == 409


def test_resume_generate_requires_format_confirm():
    project = _project("outline_locked")
    db = _db_with_project(project)

    with (
        patch("routers.generate.spawn_async", return_value=True) as spawn,
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
        patch("routers.generate.try_acquire_job", return_value=True),
        patch("routers.generate.release_job"),
        patch("routers.generate.reset_queue"),
        patch("routers.generate.spawn_async", return_value=True) as spawn,
        patch("routers.generate._require_format_confirmed"),
    ):
        result = resume_generate("p-gen", db)

    assert result["success"] is True
    assert project.status == "generating"
    spawn.assert_called_once()
    assert spawn.call_args.kwargs.get("dedupe_key") == "generate:p-gen"
    assert spawn.call_args.kwargs.get("already_acquired") is True


def _db_for_single_chapter(project: Project, chapter: TechOutline):
    """mock：先查章节再查项目（generate_single_chapter 顺序）。"""
    db = MagicMock()

    def query_side_effect(model):
        q = MagicMock()
        if model is TechOutline:
            q.filter.return_value.first.return_value = chapter
            return q
        if model is Project:
            q.filter.return_value.first.return_value = project
            return q
        q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect
    return db


def test_generate_single_chapter_rejects_when_batch_generating():
    project = _project("generating")
    chapter = TechOutline(
        id="c1",
        project_id=project.id,
        title="第一章",
        is_leaf=1,
        is_locked=1,
    )
    db = _db_for_single_chapter(project, chapter)

    with pytest.raises(HTTPException) as exc:
        generate_single_chapter(db, project.id, chapter.id)

    assert exc.value.status_code == 409
    assert "批量生成进行中" in exc.value.detail


def test_generate_chapter_router_rejects_when_batch_generating():
    project = _project("generating")
    chapter = TechOutline(
        id="c1",
        project_id=project.id,
        title="第一章",
        is_leaf=1,
        is_locked=1,
    )
    db = _db_for_single_chapter(project, chapter)

    with pytest.raises(HTTPException) as exc:
        generate_chapter(project.id, chapter.id, db)

    assert exc.value.status_code == 409


def test_regenerate_chapter_router_rejects_when_batch_generating():
    project = _project("generating")
    chapter = TechOutline(
        id="c1",
        project_id=project.id,
        title="第一章",
        is_leaf=1,
        is_locked=1,
    )
    db = _db_for_single_chapter(project, chapter)

    with pytest.raises(HTTPException) as exc:
        regenerate_chapter(chapter.id, db)

    assert exc.value.status_code == 409

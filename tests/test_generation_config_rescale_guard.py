"""generation-config：不可重算阶段不得只改篇幅展示配置。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from db.models import Project
from routers.outline import GenerationConfigUpdate, update_generation_config_api
from services.generation_config import get_generation_config
from services.project_meta import get_meta, set_meta


def _mock_db(project: Project) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project
    return db


def test_generating_status_ignores_custom_total_words_config_write():
    """generating 不可重算时，不得只写自定义字数配置造成 UI 与章节脱节。"""
    project = Project(
        id="p-gen",
        name="t",
        status="generating",
        created_at=datetime(2026, 1, 1),
        extra_params="{}",
    )
    body = GenerationConfigUpdate(custom_word_count=True, custom_total_words=52000)
    with (
        patch("routers.outline.scale_leaves_to_total_words") as scale,
        patch("routers.outline._build_generation_payload", return_value={"ok": True}),
    ):
        update_generation_config_api("p-gen", body, db=_mock_db(project))

    scale.assert_not_called()
    cfg = get_generation_config(project)
    assert cfg.get("custom_word_count") is False
    assert cfg.get("custom_total_words") is None


def test_planning_status_applies_custom_total_words():
    project = Project(
        id="p-plan",
        name="t",
        status="planning",
        created_at=datetime(2026, 1, 1),
        extra_params="{}",
    )
    body = GenerationConfigUpdate(custom_word_count=True, custom_total_words=52000)
    with (
        patch("routers.outline.scale_leaves_to_total_words") as scale,
        patch("routers.outline._build_generation_payload", return_value={"ok": True}),
    ):
        update_generation_config_api("p-plan", body, db=_mock_db(project))

    scale.assert_called_once()
    cfg = get_generation_config(project)
    assert cfg.get("custom_word_count") is True
    assert cfg.get("custom_total_words") == 52000


def test_generating_status_ignores_target_pages_meta_write():
    """generating 不可重算时，不得只改 target_pages 造成估字与章节脱节。"""
    project = Project(
        id="p-gen-pages",
        name="t",
        status="generating",
        created_at=datetime(2026, 1, 1),
        extra_params="{}",
    )
    set_meta(project, target_pages=40)
    body = GenerationConfigUpdate(target_pages=80, custom_word_count=False)
    with (
        patch("routers.outline.reapply_outline_generation_mode") as reapply,
        patch("routers.outline._build_generation_payload", return_value={"ok": True}),
    ):
        update_generation_config_api("p-gen-pages", body, db=_mock_db(project))

    reapply.assert_not_called()
    assert int(get_meta(project).get("target_pages") or 0) == 40


def test_outline_locked_status_applies_target_pages():
    project = Project(
        id="p-locked-pages",
        name="t",
        status="outline_locked",
        created_at=datetime(2026, 1, 1),
        extra_params="{}",
    )
    set_meta(project, target_pages=40)
    body = GenerationConfigUpdate(target_pages=80, custom_word_count=False)
    with (
        patch("routers.outline.reapply_outline_generation_mode") as reapply,
        patch("routers.outline._build_generation_payload", return_value={"ok": True}),
    ):
        update_generation_config_api("p-locked-pages", body, db=_mock_db(project))

    reapply.assert_called()
    assert int(get_meta(project).get("target_pages") or 0) == 80


def test_custom_total_words_rejects_out_of_range():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GenerationConfigUpdate(custom_total_words=100)
    with pytest.raises(ValidationError):
        GenerationConfigUpdate(custom_total_words=5_000_000)
    ok = GenerationConfigUpdate(custom_total_words=52000)
    assert ok.custom_total_words == 52000


def test_target_pages_rejects_out_of_range_on_generation_config():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GenerationConfigUpdate(target_pages=1)
    with pytest.raises(ValidationError):
        GenerationConfigUpdate(target_pages=5000)
    ok = GenerationConfigUpdate(target_pages=80)
    assert ok.target_pages == 80

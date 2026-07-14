"""选区改写：必须传正文坐标，避免 str.replace 误命中重复片段。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from db.models import Project, TechOutline
from services.selection_rewrite_service import apply_selection_rewrite


def _chapter(content: str) -> TechOutline:
    return TechOutline(
        id="ch1",
        project_id="p1",
        title="测试章节",
        is_leaf=1,
        generated_content=content,
    )


def _project() -> Project:
    return Project(id="p1", name="测试工程", status="writing", created_at=datetime(2026, 1, 1))


def test_apply_selection_rewrite_uses_coordinates_not_first_match():
    content = "重复句。中间重复句。结尾。"
    # 选中第二个「重复句」
    chapter = _chapter(content)
    project = _project()
    db = MagicMock()

    with patch("services.selection_rewrite_service.rewrite_selection", return_value="已改写"):
        with patch("services.selection_rewrite_service.archive_chapter_snapshot"):
            with patch("services.selection_rewrite_service.review_chapter_content", side_effect=lambda _db, _p, ch: ch):
                updated, selected, new_text = apply_selection_rewrite(
                    db,
                    chapter,
                    project,
                    selected_text="重复句",
                    instruction="改写",
                    selection_start=6,
                    selection_end=9,
                )

    assert selected == "重复句"
    assert new_text == "已改写"
    assert updated.generated_content == "重复句。中间已改写。结尾。"


def test_apply_selection_rewrite_rejects_invalid_range():
    chapter = _chapter("只有一段正文")
    project = _project()

    with pytest.raises(HTTPException) as exc:
        apply_selection_rewrite(
            MagicMock(),
            chapter,
            project,
            selected_text="正文",
            instruction="改写",
            selection_start=99,
            selection_end=100,
        )

    assert exc.value.status_code == 400

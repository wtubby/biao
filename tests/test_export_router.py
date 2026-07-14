from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routers.export import validate_export_ready


def _leaf(title: str, content: str = "正文", status: str = "green"):
    return SimpleNamespace(
        id=f"leaf-{title}",
        parent_id=None,
        sort_order=1,
        title=title,
        is_leaf=1,
        generated_content=content,
        review_status=status,
    )


def test_validate_export_ready_accepts_green_leaf():
    validate_export_ready([_leaf("施工组织设计")])


def test_validate_export_ready_blocks_missing_content():
    with pytest.raises(HTTPException) as exc:
        validate_export_ready([_leaf("施工组织设计", content="")])

    assert exc.value.status_code == 400
    assert "未生成正文" in exc.value.detail


def test_validate_export_ready_allows_missing_content_when_flag_set():
    validate_export_ready(
        [_leaf("施工组织设计", content=""), _leaf("质量保证", content="正文")],
        allow_incomplete=True,
    )


def test_validate_export_ready_allows_incomplete_and_yellow_together():
    validate_export_ready(
        [
            _leaf("施工组织设计", content=""),
            _leaf("质量保证", content="正文", status="yellow"),
        ],
        allow_incomplete=True,
        allow_yellow=True,
    )


def test_validate_export_ready_blocks_non_green_leaf():
    with pytest.raises(HTTPException) as exc:
        validate_export_ready([_leaf("施工组织设计", status="yellow")])

    assert exc.value.status_code == 400
    assert "未通过质检" in exc.value.detail


def test_validate_export_ready_allows_yellow_when_flag_set():
    validate_export_ready(
        [_leaf("施工组织设计", status="green"), _leaf("质量保证", status="yellow")],
        allow_yellow=True,
    )


def test_validate_export_ready_blocks_red_even_with_allow_yellow():
    with pytest.raises(HTTPException) as exc:
        validate_export_ready([_leaf("施工组织设计", status="red")], allow_yellow=True)

    assert exc.value.status_code == 400
    assert "生成失败" in exc.value.detail


def test_validate_export_ready_blocks_red_even_with_allow_incomplete():
    with pytest.raises(HTTPException) as exc:
        validate_export_ready(
            [_leaf("施工组织设计", content="正文", status="red")],
            allow_incomplete=True,
        )

    assert exc.value.status_code == 400
    assert "生成失败" in exc.value.detail


def test_export_word_runs_compliance_before_assemble():
    """合规终审在组装 docx 之前执行，且有 fail 时仍返回文件（不硬阻断）。"""
    from routers.export import export_word

    project = SimpleNamespace(id="p1", name="测试工程", status="done", extra_params="{}")
    chapter = _leaf("施工组织设计")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project
    db.query.return_value.filter.return_value.all.return_value = [chapter]

    out_path = MagicMock()
    out_path.exists.return_value = True
    out_path.unlink = MagicMock()
    call_order: list[str] = []

    def _track_compliance(*_a, **_k):
        call_order.append("compliance")
        return {"passed": False, "failure_count": 2, "warning_count": 1, "markdown": "# fail"}

    def _track_assemble(*_a, **_k):
        call_order.append("assemble")
        return out_path

    with patch("routers.export.require_status"), patch(
        "routers.export.assemble_document", side_effect=_track_assemble
    ), patch(
        "routers.export.run_compliance", side_effect=_track_compliance
    ), patch("routers.export.FileResponse") as mock_file_response:
        export_word("p1", db=db)

    mock_file_response.assert_called_once()
    assert call_order == ["compliance", "assemble"]
    out_path.unlink.assert_not_called()

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.assembler_service import assemble_document


def test_assemble_document_marks_yellow_heading():
    project = SimpleNamespace(
        id="project-1",
        name="测试工程",
        voltage_level="220kV",
        capacity="2×180MVA",
        location="宜宾",
        duration_days=180,
        extra_params=None,
    )
    chapters = [
        SimpleNamespace(
            title="施工组织设计",
            level=1,
            is_leaf=1,
            generated_content="正文内容",
            review_status="yellow",
            sort_order=1,
        )
    ]

    with patch("services.assembler_service._render_cover") as mock_cover, patch(
        "services.assembler_service.append_toc_and_body_sections"
    ), patch("services.assembler_service.HeadingNumbering") as mock_numbering, patch(
        "services.assembler_service.apply_professional_styles"
    ), patch("services.assembler_service.OUTPUT_DIR", "."):
        doc = MagicMock()
        mock_cover.return_value = doc
        mock_numbering.return_value.apply = MagicMock()

        assemble_document(project, chapters, mark_yellow=True)

    doc.add_heading.assert_called_once()
    assert doc.add_heading.call_args.args[0] == "施工组织设计【待优化】"

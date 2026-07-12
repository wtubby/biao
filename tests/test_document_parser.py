"""document_parser PDF 双通道去重测试。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.document_parser import (
    ParsedItem,
    _extract_text_excluding_tables,
    _obj_center_in_bboxes,
    parse_pdf,
)


def test_parse_pdf_skips_pdfplumber_tables_on_camelot_pages(monkeypatch):
    """Camelot 已提取表格的页，pdfplumber 不再重复 extract_tables。"""
    pdfplumber_calls: list[set[int] | None] = []

    def fake_camelot(_path: Path) -> list[ParsedItem]:
        return [
            ParsedItem(text="camelot table", page=2, kind="table"),
            ParsedItem(text="camelot table 2", page=5, kind="table"),
        ]

    def fake_pdfplumber(_path: Path, *, skip_table_pages=None) -> list[ParsedItem]:
        pdfplumber_calls.append(skip_table_pages)
        return []

    monkeypatch.setattr("services.document_parser.check_ghostscript", lambda: True)
    monkeypatch.setattr("services.document_parser._health_check_pdf", lambda _p: (10, False))
    monkeypatch.setattr("services.document_parser._parse_pdf_camelot", fake_camelot)
    monkeypatch.setattr("services.document_parser._parse_pdf_pdfplumber", fake_pdfplumber)

    parse_pdf(Path("dummy.pdf"))

    assert pdfplumber_calls == [{2, 5}]


def test_parse_pdf_uses_pdfplumber_tables_when_camelot_empty(monkeypatch):
    """Camelot 无产出时，pdfplumber 仍全量提取表格。"""
    pdfplumber_calls: list[set[int] | None] = []

    def fake_pdfplumber(_path: Path, *, skip_table_pages=None) -> list[ParsedItem]:
        pdfplumber_calls.append(skip_table_pages)
        return []

    monkeypatch.setattr("services.document_parser.check_ghostscript", lambda: True)
    monkeypatch.setattr("services.document_parser._health_check_pdf", lambda _p: (3, False))
    monkeypatch.setattr("services.document_parser._parse_pdf_camelot", lambda _p: [])
    monkeypatch.setattr("services.document_parser._parse_pdf_pdfplumber", fake_pdfplumber)

    parse_pdf(Path("dummy.pdf"))

    assert pdfplumber_calls == [set()]


def test_parse_pdf_uses_pdfplumber_tables_when_no_ghostscript(monkeypatch):
    """无 Ghostscript 时，pdfplumber 全量解析。"""
    pdfplumber_calls: list[set[int] | None] = []

    def fake_pdfplumber(_path: Path, *, skip_table_pages=None) -> list[ParsedItem]:
        pdfplumber_calls.append(skip_table_pages)
        return []

    monkeypatch.setattr("services.document_parser.check_ghostscript", lambda: False)
    monkeypatch.setattr("services.document_parser._health_check_pdf", lambda _p: (3, False))
    monkeypatch.setattr("services.document_parser._parse_pdf_pdfplumber", fake_pdfplumber)

    parse_pdf(Path("dummy.pdf"))

    assert pdfplumber_calls == [set()]


def test_obj_center_in_bboxes():
    bbox = (100.0, 200.0, 400.0, 500.0)
    assert _obj_center_in_bboxes({"x0": 150, "top": 250, "x1": 160, "bottom": 260}, [bbox])
    assert not _obj_center_in_bboxes({"x0": 10, "top": 20, "x1": 20, "bottom": 30}, [bbox])


def test_extract_text_excluding_tables_filters_table_chars():
    """落在表格 bbox 内的字符不参与正文提取。"""
    page = MagicMock()
    filtered = MagicMock()
    filtered.extract_text.return_value = "正文段落保留下来了"
    page.filter.return_value = filtered
    page.extract_text.return_value = "不应直接调用"

    text = _extract_text_excluding_tables(page, [(10.0, 10.0, 100.0, 100.0)])
    assert text == "正文段落保留下来了"
    page.filter.assert_called_once()
    predicate = page.filter.call_args[0][0]
    assert predicate({"x0": 200, "top": 200, "x1": 210, "bottom": 210}) is True
    assert predicate({"x0": 20, "top": 20, "x1": 30, "bottom": 30}) is False


def test_extract_text_excluding_tables_passthrough_when_no_bboxes():
    page = MagicMock()
    page.extract_text.return_value = "整页正文"
    assert _extract_text_excluding_tables(page, []) == "整页正文"
    page.filter.assert_not_called()


def test_parse_pdf_pdfplumber_excludes_table_region_from_paragraphs(monkeypatch):
    """同一页表格文字只进 table，不进 paragraph。"""
    from services import document_parser as dp

    table = SimpleNamespace(
        bbox=(10.0, 50.0, 200.0, 150.0),
        extract=lambda: [["评分项", "分值"], ["施工组织", "10"]],
    )

    cropped = MagicMock()
    cropped.find_tables.return_value = [table]

    filtered = MagicMock()
    filtered.extract_text.return_value = "本章说明施工组织设计编制依据与适用范围。"
    cropped.filter.return_value = filtered

    page = MagicMock()
    page.width = 500
    page.height = 700
    page.within_bbox.return_value = cropped

    pdf_cm = MagicMock()
    pdf_cm.__enter__.return_value = SimpleNamespace(pages=[page])
    pdf_cm.__exit__.return_value = None
    monkeypatch.setattr(dp.pdfplumber, "open", lambda _p: pdf_cm)

    items = dp._parse_pdf_pdfplumber(Path("dummy.pdf"))
    tables = [i for i in items if i.kind == "table"]
    paragraphs = [i for i in items if i.kind == "paragraph"]
    assert len(tables) == 1
    assert "施工组织" in tables[0].text
    assert len(paragraphs) == 1
    assert "编制依据" in paragraphs[0].text
    assert "分值" not in paragraphs[0].text
    cropped.filter.assert_called_once()

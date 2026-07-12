"""Word 版式：目录与页码。"""

from docx import Document
from docx.oxml.ns import qn

from services.word_styling import (
    append_toc_and_body_sections,
    create_cover_document,
    enable_auto_update_fields,
)


def test_append_toc_and_body_sections_adds_toc_and_extra_section():
    doc = create_cover_document("测试工程", {"project_date": "2026年01月01日"})
    initial_sections = len(doc.sections)
    append_toc_and_body_sections(doc)
    assert len(doc.sections) >= initial_sections + 1
    texts = [p.text for p in doc.paragraphs]
    assert any("目录" in t for t in texts)
    assert any("自动更新" in t for t in texts)


def test_enable_auto_update_fields_sets_setting():
    doc = Document()
    enable_auto_update_fields(doc)
    settings = doc.settings.element
    node = settings.find(qn("w:updateFields"))
    assert node is not None
    assert node.get(qn("w:val")) == "true"
    # 幂等：再次调用不重复插入
    enable_auto_update_fields(doc)
    assert len(settings.findall(qn("w:updateFields"))) == 1

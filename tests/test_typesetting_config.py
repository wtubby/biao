"""自定义排版参数。"""

from docx import Document

from db.models import Project
from services.generation_config import update_generation_config
from services.typesetting_config import (
    DEFAULT_TYPESETTING,
    TypesettingNumbering,
    apply_typesetting_styles,
    default_typesetting,
    get_typesetting,
    normalize_typesetting,
)


def test_default_typesetting_matches_shenjuan_style():
    ts = default_typesetting()
    assert ts["h1"]["font"] == "黑体"
    assert ts["h1"]["font_size"] == "小三"
    assert ts["h1"]["align"] == "center"
    assert ts["h1"]["number_format"] == "cn_dun"
    assert ts["h2"]["number_format"] == "cn_paren_dun"
    assert ts["body"]["first_line_indent"] == 2


def test_normalize_typesetting_clamps_indent():
    raw = {"body": {"first_line_indent": 99, "font": "未知字体"}}
    ts = normalize_typesetting(raw)
    assert ts["body"]["first_line_indent"] == 8
    assert ts["body"]["font"] == "宋体"


def test_get_typesetting_from_project():
    project = Project(id="p1", extra_params="{}")
    update_generation_config(project, typesetting={"h1": {"align": "right"}})
    ts = get_typesetting(project)
    assert ts["h1"]["align"] == "right"
    assert ts["h2"]["number_format"] == DEFAULT_TYPESETTING["h2"]["number_format"]


def test_typesetting_numbering_registers_num_pr():
    doc = Document()
    ts = default_typesetting()
    numbering = TypesettingNumbering(doc, ts)
    assert numbering.enabled
    para = doc.add_heading("测试标题", level=1)
    numbering.apply(para, 1)
    p_pr = para._p.pPr
    assert p_pr is not None
    from docx.oxml.ns import qn
    assert p_pr.find(qn("w:numPr")) is not None


def test_apply_typesetting_styles_body_indent():
    doc = Document()
    para = doc.add_paragraph("正文段落示例。")
    ts = default_typesetting()
    apply_typesetting_styles(doc, ts)
    assert para.paragraph_format.first_line_indent is not None
    assert para.paragraph_format.first_line_indent.pt == 24  # 2 字符 × 小四 12pt

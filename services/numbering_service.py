"""Word 章节标题多级编号（OOXML numbering / numPr）。"""

from __future__ import annotations

from dataclasses import dataclass

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from config import HEADING_NUMBERING_PRESET
from services.project_meta import get_meta

MAX_HEADING_LEVELS = 4
TWIPS_PER_LEVEL = 420  # 约 0.74cm 悬挂缩进


@dataclass(frozen=True)
class _LevelDef:
    num_fmt: str
    lvl_text: str
    suffix: str = " "


# 预设与 Word「多级列表」常见样式对应
HEADING_NUMBERING_PRESETS: dict[str, list[_LevelDef]] = {
    "decimal": [
        _LevelDef("decimal", "%1"),
        _LevelDef("decimal", "%1.%2"),
        _LevelDef("decimal", "%1.%2.%3"),
        _LevelDef("decimal", "%1.%2.%3.%4"),
    ],
    "chapter_cn": [
        _LevelDef("decimal", "第%1章"),
        _LevelDef("decimal", "第%2节"),
        _LevelDef("chineseCounting", "%3、"),
        _LevelDef("decimal", "（%4）"),
    ],
    "outline_mixed": [
        _LevelDef("decimal", "第%1章"),
        _LevelDef("decimal", "%1.%2"),
        _LevelDef("decimal", "%1.%2.%3"),
        _LevelDef("decimal", "（%4）"),
    ],
}


def list_heading_numbering_presets() -> list[dict[str, str]]:
    """供 API / 前端展示用的预设列表。"""
    labels = {
        "none": "无编号",
        "decimal": "1 / 1.1 / 1.1.1",
        "chapter_cn": "第X章 / 第X节 / 一、",
        "outline_mixed": "第X章 / X.X / X.X.X",
    }
    return [
        {"id": key, "label": labels.get(key, key)}
        for key in ["none", *HEADING_NUMBERING_PRESETS]
    ]


def resolve_heading_numbering_preset(project=None) -> str:
    """项目 meta 优先，其次全局 config，默认 decimal。"""
    preset = HEADING_NUMBERING_PRESET
    if project is not None:
        meta_preset = get_meta(project).get("heading_numbering_preset")
        if isinstance(meta_preset, str) and meta_preset.strip():
            preset = meta_preset.strip()
    if preset == "none":
        return "none"
    if preset in HEADING_NUMBERING_PRESETS:
        return preset
    return "decimal"


def _next_numbering_id(root, tag: str, attr: str) -> int:
    vals = [
        int(el.get(attr))
        for el in root.findall(qn(tag))
        if el.get(attr) is not None
    ]
    return max(vals, default=0) + 1


def _make_lvl(ilvl: int, level_def: _LevelDef) -> OxmlElement:
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), str(ilvl))

    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    lvl.append(start)

    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), level_def.num_fmt)
    lvl.append(num_fmt)

    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), level_def.lvl_text + level_def.suffix)
    lvl.append(lvl_text)

    lvl_jc = OxmlElement("w:lvlJc")
    lvl_jc.set(qn("w:val"), "left")
    lvl.append(lvl_jc)

    if ilvl > 0:
        lvl_restart = OxmlElement("w:lvlRestart")
        lvl_restart.set(qn("w:val"), str(ilvl - 1))
        lvl.append(lvl_restart)

    p_pr = OxmlElement("w:pPr")
    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), str(TWIPS_PER_LEVEL * ilvl))
    ind.set(qn("w:hanging"), str(TWIPS_PER_LEVEL))
    p_pr.append(ind)
    lvl.append(p_pr)

    return lvl


def _register_multilevel_numbering(doc: Document, preset: str) -> int:
    """在文档 numbering 部件注册多级方案，返回 numId。"""
    levels = HEADING_NUMBERING_PRESETS[preset]
    numbering_elm = doc.part.numbering_part.element

    abstract_num_id = _next_numbering_id(numbering_elm, "w:abstractNum", qn("w:abstractNumId"))
    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), str(abstract_num_id))

    multi_level_type = OxmlElement("w:multiLevelType")
    multi_level_type.set(qn("w:val"), "multilevel")
    abstract_num.append(multi_level_type)

    for ilvl, level_def in enumerate(levels):
        abstract_num.append(_make_lvl(ilvl, level_def))

    numbering_elm.append(abstract_num)

    num_id = _next_numbering_id(numbering_elm, "w:num", qn("w:numId"))
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_num_id_el = OxmlElement("w:abstractNumId")
    abstract_num_id_el.set(qn("w:val"), str(abstract_num_id))
    num.append(abstract_num_id_el)
    numbering_elm.append(num)

    return num_id


class HeadingNumbering:
    """为章节标题段落挂载 Word 多级编号。"""

    def __init__(self, doc: Document, preset: str = "decimal"):
        self.preset = preset
        self._num_id: int | None = None
        if preset != "none" and preset in HEADING_NUMBERING_PRESETS:
            self._num_id = _register_multilevel_numbering(doc, preset)

    @property
    def enabled(self) -> bool:
        return self._num_id is not None

    def apply(self, paragraph: Paragraph, outline_level: int) -> None:
        if self._num_id is None:
            return
        ilvl = min(max(outline_level, 1), MAX_HEADING_LEVELS) - 1
        p_pr = paragraph._p.get_or_add_pPr()
        # 避免重复挂载
        if p_pr.find(qn("w:numPr")) is not None:
            return
        num_pr = OxmlElement("w:numPr")
        ilvl_el = OxmlElement("w:ilvl")
        ilvl_el.set(qn("w:val"), str(ilvl))
        num_pr.append(ilvl_el)
        num_id_el = OxmlElement("w:numId")
        num_id_el.set(qn("w:val"), str(self._num_id))
        num_pr.append(num_id_el)
        p_pr.append(num_pr)

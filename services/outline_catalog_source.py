"""目录来源：按招标评分点 / 按参考格式。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Project, TechRequirement
from services.catalog_parser import parse_catalog_text
from services.project_meta import (
    get_meta,
    get_outline_catalog_text,
    is_valid_outline_catalog,
    set_meta,
    set_outline_catalog,
)
from services.tender_detail_service import get_tender_detail

CATALOG_SOURCE_SCORE = "score_points"
CATALOG_SOURCE_REFERENCE = "reference_format"
CATALOG_SOURCES = (CATALOG_SOURCE_SCORE, CATALOG_SOURCE_REFERENCE)

_CN_DIGITS = "〇一二三四五六七八九"


def _cn_index(n: int) -> str:
    if n <= 0:
        return str(n)
    if n <= 10:
        return "十" if n == 10 else _CN_DIGITS[n]
    if n < 20:
        return f"十{_CN_DIGITS[n - 10]}"
    tens, ones = divmod(n, 10)
    tens_part = "" if tens == 1 else _CN_DIGITS[tens]
    ones_part = _CN_DIGITS[ones] if ones else ""
    return f"{tens_part}十{ones_part}"


def get_catalog_source(project: Project) -> str:
    source = str(get_meta(project).get("outline_catalog_source") or "").strip()
    if source in CATALOG_SOURCES:
        return source
    return CATALOG_SOURCE_SCORE


def set_catalog_source(project: Project, source: str) -> None:
    if source not in CATALOG_SOURCES:
        raise ValueError("无效的目录来源")
    set_meta(project, outline_catalog_source=source)


def get_bid_reference_catalog_text(project: Project) -> str:
    detail = get_tender_detail(project)
    return str(detail.get("bid_reference_catalog") or "").strip()


def build_score_points_catalog_text(requirements: list[TechRequirement]) -> str:
    lines: list[str] = []
    idx = 0
    for req in requirements:
        title = (req.requirement_title or "").strip()
        if not title:
            continue
        idx += 1
        lines.append(f"（{_cn_index(idx)}）{title}")
    return "\n".join(lines)


def _preview_dict(
    *,
    source: str,
    text: str,
    available: bool,
    hint: str | None = None,
) -> dict:
    catalog = parse_catalog_text(text) if text.strip() else []
    return {
        "source": source,
        "text": text,
        "count": len(catalog),
        "available": available,
        "hint": hint,
    }


def preview_catalog_source(
    project: Project,
    requirements: list[TechRequirement],
    source: str,
) -> dict:
    if source == CATALOG_SOURCE_SCORE:
        text = build_score_points_catalog_text(requirements)
        titled = [r for r in requirements if (r.requirement_title or "").strip()]
        available = len(titled) >= 1
        if available:
            hint = None
        else:
            hint = (
                "当前无已确认评分项，无法从评分点自动填目录。"
                "请切换「按参考格式生成」或手动粘贴目录；评分项仅作参考，不影响后续大纲深化。"
            )
        return _preview_dict(source=source, text=text, available=available, hint=hint)

    extracted = get_bid_reference_catalog_text(project)
    manual = get_outline_catalog_text(project).strip()
    # 参考格式以本标书提取结果为准；无提取时才回落到已保存/手写目录
    text = extracted or manual
    catalog = parse_catalog_text(text) if text else []
    parsed_ok = is_valid_outline_catalog(catalog)
    # available = 本标书有可自动填入的参考原文（即使编号不规范，也允许切换后编辑）
    available = bool(extracted.strip())
    hint = None
    if not extracted:
        hint = (
            "本标书暂无「投标文件参考格式」目录。"
            "请回核对页补充，或在此手动粘贴招标文件「投标文件格式 / 技术文件组成」章节。"
        )
        available = False
    elif not parsed_ok:
        hint = "已提取到本标书参考格式原文，但章节编号未能完整识别；切换后将填入原文，请编辑后保存"
        available = True
    return _preview_dict(source=source, text=text, available=available, hint=hint)


def build_catalog_previews(project: Project, requirements: list[TechRequirement]) -> dict:
    return {
        CATALOG_SOURCE_SCORE: preview_catalog_source(project, requirements, CATALOG_SOURCE_SCORE),
        CATALOG_SOURCE_REFERENCE: preview_catalog_source(project, requirements, CATALOG_SOURCE_REFERENCE),
    }


def apply_catalog_source(
    project: Project,
    requirements: list[TechRequirement],
    source: str,
) -> dict:
    set_catalog_source(project, source)
    preview = preview_catalog_source(project, requirements, source)

    if source == CATALOG_SOURCE_SCORE:
        if not preview["available"]:
            raise ValueError(preview.get("hint") or "无法按评分点生成目录")
        text = preview["text"]
        catalog = parse_catalog_text(text)
        set_outline_catalog(project, text, catalog)
        return {
            "source": source,
            "text": text,
            "catalog": catalog,
            "count": len(catalog),
            "applied": True,
            "message": f"已按 {len(requirements)} 条评分项生成目录",
        }

    extracted = get_bid_reference_catalog_text(project)
    manual = get_outline_catalog_text(project).strip()
    if extracted:
        catalog = parse_catalog_text(extracted)
        if is_valid_outline_catalog(catalog):
            set_outline_catalog(project, extracted, catalog)
            return {
                "source": source,
                "text": extracted,
                "catalog": catalog,
                "count": len(catalog),
                "applied": True,
                "message": "已应用本标书的投标文件参考格式目录",
            }
        # 有原文但编号不规范：仍填入文本框供人工编辑，不阻断切换
        return {
            "source": source,
            "text": extracted,
            "catalog": [],
            "count": 0,
            "applied": False,
            "message": "已填入本标书参考格式原文，章节编号需人工核对后保存",
        }

    if manual:
        catalog = parse_catalog_text(manual)
        if is_valid_outline_catalog(catalog):
            return {
                "source": source,
                "text": manual,
                "catalog": catalog,
                "count": len(catalog),
                "applied": False,
                "message": "本标书暂无参考格式；已保留当前目录，请核对或粘贴招标文件格式章节后保存",
            }
        return {
            "source": source,
            "text": manual,
            "catalog": [],
            "count": 0,
            "applied": False,
            "message": "本标书暂无参考格式；请编辑目录编号格式后保存",
        }

    return {
        "source": source,
        "text": "",
        "catalog": [],
        "count": 0,
        "applied": False,
        "message": preview.get("hint") or "本标书暂无参考格式，请粘贴目录后保存",
    }


def get_catalog_payload(db: Session, project: Project) -> dict:
    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id, TechRequirement.status == "confirmed")
        .all()
    )
    from services.outline_service import get_user_catalog

    base = get_user_catalog(project)
    source = get_catalog_source(project)
    previews = build_catalog_previews(project, requirements)
    return {
        **base,
        "source": source,
        "previews": previews,
    }

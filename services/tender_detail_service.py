"""钛投标式招标文件解析结果：投标人须知 / 商务·技术要求 / 资格审查 / 评分要求。"""

from __future__ import annotations

from typing import Any

from db.models import Project
from domains.registry import DEFAULT_DOMAIN
from services.duration_text import parse_duration_days_from_text
from services.project_meta import get_meta, set_meta

QUALIFICATION_TABS = ("资格性审查", "符合性审查", "废标项")

PROTECTABLE_FIELDS = (
    "name", "voltage_level", "capacity", "location", "duration_days",
    "project_type", "contract_mode", "engineering_domain", "budget_yuan", "target_pages",
)


def empty_notice() -> dict[str, Any]:
    return {
        "project_name": None,
        "project_code": None,
        "package_name": None,
        "package_no": None,
        "budget_wan": None,
        "budget_yuan": None,
        "tenderer": None,
        "agency": None,
        "bid_domain": None,
        "overview": None,
        "sme_targeted": None,
        "blind_bid": None,
        "duration_text": None,
        "location": None,
        # 技术标写作仍需要的扩展字段
        "project_type": None,
        "contract_mode": None,
        "voltage_level": None,
        "capacity": None,
        "target_pages": None,
    }


def empty_tender_detail() -> dict[str, Any]:
    return {
        "notice": empty_notice(),
        "commerce_requirements": "",
        "service_requirements": "",
        "bid_reference_catalog": "",
        "qualification_items": [],
        "commerce_scores": [],
    }


def mark_fields_manually_confirmed(project: Project, fields: list[str]) -> None:
    """标记这些项目字段已被用户手动确认过，之后解析新文件时不再自动覆盖。"""
    current = set(get_meta(project).get("manually_confirmed_fields") or [])
    current.update(f for f in fields if f in PROTECTABLE_FIELDS)
    set_meta(project, manually_confirmed_fields=sorted(current))


def _is_manually_confirmed(project: Project, field: str) -> bool:
    return field in (get_meta(project).get("manually_confirmed_fields") or [])


def get_tender_detail(project: Project) -> dict[str, Any]:
    meta = get_meta(project)
    raw = meta.get("tender_detail")
    if not isinstance(raw, dict):
        return empty_tender_detail()
    return _normalize_tender_detail(raw)


def set_tender_detail(project: Project, detail: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_tender_detail(detail)
    set_meta(project, tender_detail=normalized)
    return normalized


def _normalize_notice(raw: dict | None) -> dict[str, Any]:
    base = empty_notice()
    if not isinstance(raw, dict):
        return base
    for key in base:
        if key in raw and raw[key] is not None:
            base[key] = raw[key]
    return base


def _normalize_qualification_items(items: list | None) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        source_text = str(item.get("source_text") or "").strip()
        description = str(item.get("description") or "").strip()
        # 兼容旧数据：无 source_text 时用 description 顶上；优先保留原文
        if not source_text and description:
            source_text = description
        if not description and source_text:
            description = source_text
        if not source_text and not description:
            continue
        seq = item.get("seq")
        try:
            seq = int(seq) if seq is not None else idx
        except (TypeError, ValueError):
            seq = idx
        source_page = item.get("source_page")
        try:
            source_page = int(source_page) if source_page is not None else None
        except (TypeError, ValueError):
            source_page = None
        normalized.append({
            "seq": seq,
            "item_label": str(item.get("item_label") or item.get("category") or "废标项").strip(),
            "description": description or source_text,
            "source_text": source_text or description,
            "source_page": source_page,
        })
    normalized.sort(key=lambda x: x["seq"])
    return normalized


def _normalize_score_items(items: list | None) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("requirement_title") or "").strip()
        criteria = str(item.get("criteria") or item.get("source_text") or "").strip()
        if not title and not criteria:
            continue
        score_value = item.get("score_value")
        try:
            score_value = float(score_value) if score_value is not None else None
        except (TypeError, ValueError):
            score_value = None
        normalized.append({
            "title": title or "未命名评分项",
            "criteria": criteria,
            "score_value": score_value,
        })
    return normalized


def _normalize_tender_detail(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "notice": _normalize_notice(raw.get("notice")),
        "commerce_requirements": str(raw.get("commerce_requirements") or ""),
        "service_requirements": str(raw.get("service_requirements") or ""),
        "bid_reference_catalog": str(raw.get("bid_reference_catalog") or ""),
        "qualification_items": _normalize_qualification_items(raw.get("qualification_items")),
        "commerce_scores": _normalize_score_items(raw.get("commerce_scores")),
    }


def merge_tender_detail(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    inc = _normalize_tender_detail(incoming)
    notice = target.setdefault("notice", empty_notice())
    for key, value in inc["notice"].items():
        if value is not None and value != "" and not notice.get(key):
            notice[key] = value

    for field in ("commerce_requirements", "service_requirements", "bid_reference_catalog"):
        cur = (target.get(field) or "").strip()
        new = (inc.get(field) or "").strip()
        if new and len(new) > len(cur):
            target[field] = new

    seen_keys = {
        (str(i.get("source_text") or i.get("description") or "").strip())
        for i in target.get("qualification_items") or []
    }
    for item in inc["qualification_items"]:
        key = str(item.get("source_text") or item.get("description") or "").strip()
        if key and key not in seen_keys:
            target.setdefault("qualification_items", []).append(item)
            seen_keys.add(key)

    seen_titles = {str(i.get("title") or "").strip() for i in target.get("commerce_scores") or []}
    for item in inc["commerce_scores"]:
        title = item["title"]
        if title not in seen_titles:
            target.setdefault("commerce_scores", []).append(item)
            seen_titles.add(title)


def apply_notice_to_project(
    project: Project,
    notice: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    """将 notice 字段回填到 project。force=True 时忽略手动确认保护（用户表单保存用）。"""
    def _can_write(field: str) -> bool:
        return force or not _is_manually_confirmed(project, field)

    if notice.get("project_name") and _can_write("name"):
        project.name = notice["project_name"]
    if notice.get("voltage_level") and _can_write("voltage_level"):
        project.voltage_level = notice["voltage_level"]
    if notice.get("capacity") and _can_write("capacity"):
        project.capacity = notice["capacity"]
    if notice.get("location") and _can_write("location"):
        project.location = notice["location"]
    if notice.get("duration_text") and _can_write("duration_days"):
        days = _parse_duration_days(notice["duration_text"])
        if days is not None:
            project.duration_days = days

    meta_fields: dict[str, Any] = {}
    if notice.get("project_type") and _can_write("project_type"):
        meta_fields["project_type"] = notice["project_type"]
    if notice.get("contract_mode") and _can_write("contract_mode"):
        meta_fields["contract_mode"] = notice["contract_mode"]
    if notice.get("bid_domain") and _can_write("engineering_domain"):
        meta_fields["engineering_domain"] = notice["bid_domain"]
    if notice.get("budget_yuan") is not None and _can_write("budget_yuan"):
        try:
            meta_fields["budget_yuan"] = float(notice["budget_yuan"])
        except (TypeError, ValueError):
            pass
    if notice.get("target_pages") is not None and _can_write("target_pages"):
        try:
            meta_fields["target_pages"] = int(notice["target_pages"])
        except (TypeError, ValueError):
            pass
    if meta_fields:
        set_meta(project, **meta_fields)


def sync_project_to_notice(project: Project) -> None:
    """把 project / meta 上的工程信息写回 tender_detail.notice，避免两表单显示不一致。"""
    detail = get_tender_detail(project)
    notice = detail.setdefault("notice", empty_tender_detail()["notice"])
    meta = get_meta(project)

    notice["project_name"] = project.name
    notice["voltage_level"] = project.voltage_level
    notice["capacity"] = project.capacity
    notice["location"] = project.location
    if project.duration_days is not None:
        notice["duration_text"] = f"{project.duration_days}个日历天"
    notice["project_type"] = meta.get("project_type")
    notice["contract_mode"] = meta.get("contract_mode")
    notice["bid_domain"] = meta.get("engineering_domain") or DEFAULT_DOMAIN
    if meta.get("target_pages") is not None:
        notice["target_pages"] = meta.get("target_pages")
    if meta.get("extra_notes") is not None:
        notice["overview"] = meta.get("extra_notes")
    if meta.get("budget_yuan") is not None:
        notice["budget_yuan"] = meta.get("budget_yuan")
        try:
            notice["budget_wan"] = f"{float(meta['budget_yuan']) / 10000:.4f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            pass

    detail["notice"] = notice
    set_tender_detail(project, detail)


def _parse_duration_days(text: str) -> int | None:
    return parse_duration_days_from_text(text)


def save_tender_detail_from_extraction(project: Project, result: dict) -> dict[str, Any]:
    raw = result.get("tender_detail")
    if not isinstance(raw, dict):
        raw = {}
    detail = _normalize_tender_detail(raw)

    gp = result.get("global_params") or {}
    notice = detail["notice"]
    mapping = {
        "project_name": gp.get("name"),
        "project_type": gp.get("project_type"),
        "contract_mode": gp.get("contract_mode"),
        "bid_domain": gp.get("engineering_domain"),
        "voltage_level": gp.get("voltage_level"),
        "capacity": gp.get("scale") or gp.get("capacity"),
        "budget_yuan": gp.get("budget_yuan"),
        "overview": gp.get("extra_notes"),
        "location": gp.get("location"),
    }
    if gp.get("duration_days") is not None:
        mapping["duration_text"] = f"{gp['duration_days']}个日历天"
    if gp.get("budget_yuan") is not None:
        try:
            mapping["budget_wan"] = f"{float(gp['budget_yuan']) / 10000:.4f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            pass
    for key, value in mapping.items():
        if value is not None and value != "" and not notice.get(key):
            notice[key] = value

    detail["notice"] = notice
    set_tender_detail(project, detail)
    apply_notice_to_project(project, notice)
    return detail


def filter_qualification_items(items: list[dict], tab: str) -> list[dict]:
    if tab == "资格性审查":
        return [i for i in items if "资格" in (i.get("item_label") or "")]
    if tab == "符合性审查":
        return [i for i in items if "符合" in (i.get("item_label") or "")]
    if tab == "废标项":
        return [
            i for i in items
            if "资格" not in (i.get("item_label") or "") and "符合" not in (i.get("item_label") or "")
        ]
    return items

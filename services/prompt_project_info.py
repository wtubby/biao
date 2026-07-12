"""提示词用全局工程信息：大纲 / 规划 / 正文共用同一套中文字段。"""

from __future__ import annotations

from db.models import Project
from domains.registry import DEFAULT_DOMAIN
from services.project_meta import get_meta

# (字段键, 用户可见标签) — 大纲生成前完整性校验
REQUIRED_PROMPT_GLOBAL_FIELDS = [
    ("工程名称", "工程名称"),
    ("项目类型", "项目类型"),
    ("电压等级", "电压等级"),
    ("建设地点", "建设地点"),
    ("总工期", "总工期"),
]


def build_prompt_global_params(project: Project) -> dict:
    """组装注入 LLM 提示词的全局工程信息（中文字段）。"""
    meta = get_meta(project)
    domain = meta.get("engineering_domain") or DEFAULT_DOMAIN
    params: dict = {
        "工程名称": project.name,
        "工程领域": domain,
        "项目类型": meta.get("project_type"),
        "电压等级": project.voltage_level,
        "工程规模": project.capacity,
        "总工期": project.duration_days,
        "建设地点": project.location,
    }
    contract_mode = meta.get("contract_mode")
    if contract_mode:
        params["承包方式"] = contract_mode
    extra_notes = (meta.get("extra_notes") or "").strip()
    if extra_notes:
        params["补充说明"] = extra_notes
    return params


def validate_prompt_global_params(params: dict) -> None:
    """校验提示词用全局工程信息是否完整。"""
    from domains.registry import resolve_domain

    domain_key = resolve_domain(params.get("工程领域")).key
    missing: list[str] = []
    for field, label in REQUIRED_PROMPT_GLOBAL_FIELDS:
        if field == "电压等级" and domain_key != DEFAULT_DOMAIN:
            continue
        value = params.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(label)
    if missing:
        raise ValueError(
            f"全局工程信息未填写完整：{', '.join(missing)}，请先完善后再生成大纲"
        )

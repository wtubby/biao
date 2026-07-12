"""工程领域注册表：单一真相源，供写作人设、指南、QA 规范前缀等复用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from config import BASE_DIR

DEFAULT_DOMAIN = "电力工程"

_REGISTRY_PATH = Path(BASE_DIR) / "domains" / "domains.yaml"


@dataclass(frozen=True)
class DomainSpec:
    key: str
    label: str
    identity_prompt: str
    guide_file: str | None = None
    outline_catalog: str | None = None
    standard_prefixes: list[str] = field(default_factory=list)
    detect_keywords: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


def _fallback_identity(domain: str) -> str:
    return (
        f"你是资深工程技术方案撰写专家，专精于{domain}领域的设计、施工、验收全流程，"
        "能够按照该领域行业规范撰写投标技术方案。"
    )


@lru_cache(maxsize=1)
def load_domains() -> dict[str, DomainSpec]:
    raw = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    result: dict[str, DomainSpec] = {}
    for item in raw.get("domains") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        spec = DomainSpec(
            key=str(item["key"]).strip(),
            label=str(item.get("label") or item["key"]).strip(),
            identity_prompt=str(item.get("identity_prompt") or "").strip()
            or _fallback_identity(str(item["key"]).strip()),
            guide_file=(str(item["guide_file"]).strip() if item.get("guide_file") else None),
            outline_catalog=(
                str(item["outline_catalog"]).strip() if item.get("outline_catalog") else None
            ),
            standard_prefixes=[str(x).strip() for x in (item.get("standard_prefixes") or []) if x],
            detect_keywords=[str(x).strip() for x in (item.get("detect_keywords") or []) if x],
            aliases=[str(x).strip() for x in (item.get("aliases") or []) if x],
        )
        result[spec.key] = spec
        for alias in spec.aliases:
            result[alias] = spec
    if DEFAULT_DOMAIN not in result:
        result[DEFAULT_DOMAIN] = DomainSpec(
            key=DEFAULT_DOMAIN,
            label=DEFAULT_DOMAIN,
            identity_prompt=_fallback_identity(DEFAULT_DOMAIN),
            guide_file="电力EPC技术标写作指南.md",
            standard_prefixes=["GB", "DL", "QGDW", "JGJ", "NB"],
        )
    return result


def resolve_domain(raw: str | None) -> DomainSpec:
    domains = load_domains()
    key = (raw or "").strip()
    if not key:
        return domains[DEFAULT_DOMAIN]
    if key in domains:
        return domains[key]
    # 未注册领域：动态兜底，不写入缓存表，避免污染正式 key 列表
    return DomainSpec(
        key=key,
        label=key,
        identity_prompt=_fallback_identity(key),
        guide_file=None,
        standard_prefixes=["GB", "JGJ"],
    )


def list_domain_keys() -> list[dict[str, str]]:
    """去重后的领域 key 列表，供前端下拉框使用。"""
    seen: dict[str, str] = {}
    for spec in load_domains().values():
        seen[spec.key] = spec.label
    # 保持 yaml 中声明顺序：按首次出现顺序
    ordered: list[dict[str, str]] = []
    for spec in load_domains().values():
        if any(item["key"] == spec.key for item in ordered):
            continue
        ordered.append({"key": spec.key, "label": seen[spec.key]})
    return ordered


def clear_domain_cache() -> None:
    load_domains.cache_clear()

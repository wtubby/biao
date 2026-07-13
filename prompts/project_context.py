"""全书稳定上下文块：Writer / QA 共用同一字符串以利于 DeepSeek 前缀缓存。"""

from __future__ import annotations

import json

from prompts.context_blocks import format_contradictions_block, format_overview_block

_MESSAGE_JOIN = "\n\n"


def build_cacheable_project_prefix(bundle: dict) -> str:
    """同项目各章共享的稳定前缀（字节级一致，Writer 与 QA 必须共用）。"""
    global_params = bundle.get("global_params") or {}
    overview_block = format_overview_block(bundle.get("project_overview") or "", style="writer")
    contra_block = format_contradictions_block(bundle.get("contradictions") or [], style="writer")

    parts: list[str] = [
        f"## 全局工程信息\n{json.dumps(global_params, ensure_ascii=False, indent=2)}",
        overview_block.rstrip() if overview_block else "",
    ]
    facts_text = (bundle.get("global_facts_text") or "").strip()
    if facts_text:
        parts.append(
            "【全局事实变量（全书保持一致，涉及时必须使用以下信息，不得自行编造）】\n"
            f"{facts_text}"
        )
    if contra_block:
        parts.append(contra_block.rstrip())

    standards_hint = (bundle.get("standards_hint") or "").strip()
    if standards_hint:
        parts.append(
            "## 写作惯例提示（非标准条文原文，仅供表述参考）\n"
            f"{standards_hint}"
        )
    blind_constraints = (bundle.get("blind_bid_constraints") or "").strip()
    if blind_constraints:
        parts.append(blind_constraints)

    return _MESSAGE_JOIN.join(p for p in parts if p.strip())

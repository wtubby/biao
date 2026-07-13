import json

from domains.registry import DEFAULT_DOMAIN
from prompts.bundle_blocks import (
    format_prior_chapters_block,
    format_retrieval_notes,
)
from prompts.context_blocks import (
    format_contradictions_block,
    format_facts_block,
    format_generation_extras,
    format_overview_block,
    format_scope_constraints,
)
from services.writing_guidance import get_chapter_constraints, get_chapter_type

_PLAN_RULES = """在正式撰写章节之前，先制定一份详细的写作规划。规划范围仅限当前章节，不得包含其他章节要点。

输出 JSON，结构如下：
{
  "key_points": ["必须覆盖的要点1", "要点2"],
  "technical_methods": ["拟采用的主要工艺/方法"],
  "data_to_include": ["需要包含的关键技术数据/参数"],
  "charts_needed": [{"type": "GANTT_DATA", "purpose": "用途说明"}],
  "word_count_target": 1000,
  "avoid": ["上一章已描述过的内容，本章不重复"],
  "retrieval_focus": ["用于二次检索的工艺/设备关键词"]
}

word_count_target 须为整数，且与用户提示中「建议篇幅约 X 字」的 X 一致，勿套用示例数值。
key_points 须覆盖本章每条评分项的「必备要素」（若有）及评分细则中的量化/管理要求；高分值项优先列入。
请直接输出 JSON 字符串，不要包含任何 Markdown 代码块包裹（如 ```json）或前后导言。"""


def get_plan_system_prompt(domain: str | None = None) -> str:
    domain = domain or DEFAULT_DOMAIN
    if domain == DEFAULT_DOMAIN:
        identity = "你是电力工程技术方案写作规划专家。"
    else:
        identity = f"你是{domain}技术方案写作规划专家，熟悉该领域施工组织与验收要求。"
    return f"{identity}\n{_PLAN_RULES}"


_OTHER_LEAF_PLAN_LIMIT = 40
_PLAN_MESSAGE_JOIN = "\n\n"


def _plan_type_hint(bundle: dict) -> str:
    chapter_title = bundle.get("chapter_title")
    chapter_type = get_chapter_type(chapter_title)
    constraints = get_chapter_constraints(chapter_title)
    if not constraints:
        return ""
    type_hint_list = [str(constraints).strip()]
    if chapter_type == "goal":
        type_hint_list.append(
            "规划时 key_points 仅列目标承诺，technical_methods 留空或填「无」，"
            "data_to_include 仅保留总工期、合同价等宏观数据，charts_needed 留空。"
        )
    elif chapter_type == "overview":
        type_hint_list.append(
            "规划时 key_points 仅列项目客观信息与特点，technical_methods 留空或填「无」，"
            "data_to_include 仅保留规模、电压等级、工期、地点等全局事实，charts_needed 留空。"
        )
    return "\n" + "\n".join(type_hint_list)


def _plan_project_context(bundle: dict) -> str:
    """同项目各章共享的稳定上下文（前置以利于 Prompt Cache）。"""
    global_params = bundle.get("global_params") or {}
    overview_block = format_overview_block(bundle.get("project_overview") or "", style="plan")
    facts_block = format_facts_block(bundle.get("global_facts_text") or "", style="plan")
    contra_block = format_contradictions_block(bundle.get("contradictions") or [], style="plan")

    parts: list[str] = [
        f"## 全局工程信息\n{json.dumps(global_params, ensure_ascii=False, indent=2)}",
        overview_block.rstrip() if overview_block else "",
        facts_block.rstrip() if facts_block else "",
        contra_block.rstrip() if contra_block else "",
    ]
    standards_hint = (bundle.get("standards_hint") or "").strip()
    if standards_hint:
        parts.append(f"## 写作惯例提示（非标准条文原文）\n{standards_hint}")
    blind_constraints = (bundle.get("blind_bid_constraints") or "").strip()
    if blind_constraints:
        parts.append(blind_constraints)

    return _PLAN_MESSAGE_JOIN.join(p for p in parts if p.strip())


def _plan_continuity_context(bundle: dict) -> str:
    return format_prior_chapters_block(bundle, style="plan").strip()


def _plan_retrieval_context(bundle: dict) -> str:
    retrieval_text = bundle.get("retrieval_text") or "（无检索素材）"
    retrieval_notes = format_retrieval_notes(bundle, inline=False)
    body = f"## 检索素材\n{retrieval_text}"
    if retrieval_notes:
        body = f"{body}\n{retrieval_notes}"
    return body.strip()


def _plan_chapter_task_body(bundle: dict) -> str:
    guidance = bundle.get("guidance") or {}
    target_words = guidance.get("target_words") or 1000
    chapter_title = bundle.get("chapter_title")
    chapter_path = bundle.get("chapter_path") or "未知"

    req_hint = (bundle.get("requirements_hint") or "").strip()
    req_hint_block = f"\n\n{req_hint}" if req_hint else ""
    matrix_context = (bundle.get("matrix_context") or "").strip()
    matrix_block = f"\n\n## 本章评分响应矩阵\n{matrix_context}\n" if matrix_context else ""
    evaluation_focus = (bundle.get("evaluation_focus") or "").strip()
    focus_block = f"\n\n{evaluation_focus}\n" if evaluation_focus else ""

    requirements_text = bundle.get("requirements_text") or "（无相关要求）"
    type_hint = _plan_type_hint(bundle)
    extras_bundle = dict(bundle)
    extras_bundle["standards_hint"] = ""
    extras_bundle["blind_bid_constraints"] = ""
    extras_block = format_generation_extras(extras_bundle, style="plan")

    base = f"""## 本章评分项
{requirements_text}{req_hint_block}{matrix_block}{focus_block}

## 章节定位
标题：{chapter_title}
路径：{chapter_path}
写作要点：{guidance.get('brief') or '无'}
内容边界：{guidance.get('content_boundary') or '无'}
建议篇幅约 {target_words} 字

## 范围约束（规划不得包含下列章节要点）
{format_scope_constraints(bundle, style="plan", limit=_OTHER_LEAF_PLAN_LIMIT)}{type_hint}

{extras_block}请输出本章写作规划 JSON。"""
    return base.strip()


def build_plan_user_messages(
    bundle: dict,
    *,
    retry_issues: list[str] | None = None,
) -> list[str]:
    """分层 user 消息：稳定上下文前置，本章规划任务置末。"""
    messages: list[str] = []
    for part in (
        _plan_project_context(bundle),
        _plan_continuity_context(bundle),
        _plan_retrieval_context(bundle),
        _plan_chapter_task_body(bundle),
    ):
        text = (part or "").strip()
        if text:
            messages.append(text)
    if retry_issues:
        issues = "\n".join(f"- {x}" for x in retry_issues)
        messages.append(
            "上次规划问题：\n"
            f"{issues}\n"
            "请输出修正后的完整 JSON。"
        )
    return messages


def build_plan_chat_messages(
    bundle: dict,
    *,
    retry_issues: list[str] | None = None,
) -> list[dict[str, str]]:
    domain = bundle.get("engineering_domain") or DEFAULT_DOMAIN
    messages: list[dict[str, str]] = [
        {"role": "system", "content": get_plan_system_prompt(domain)},
    ]
    for part in build_plan_user_messages(bundle, retry_issues=retry_issues):
        messages.append({"role": "user", "content": part})
    return messages


def build_plan_user_prompt(
    bundle: dict,
    *,
    retry_issues: list[str] | None = None,
) -> str:
    """兼容调试预览：将分层 user 消息合并为单条字符串。"""
    return _PLAN_MESSAGE_JOIN.join(
        build_plan_user_messages(bundle, retry_issues=retry_issues)
    )

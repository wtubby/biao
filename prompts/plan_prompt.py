import json

from domains.registry import DEFAULT_DOMAIN
from prompts.bundle_blocks import (
    format_prior_chapters_block,
    format_retrieval_notes,
    truncate_reference_bid,
)
from prompts.context_blocks import (
    format_contradictions_block,
    format_facts_block,
    format_generation_extras,
    format_overview_block,
    format_scope_constraints,
    format_title_list,
)
from services.writing_guidance import get_chapter_constraints, get_chapter_type

_PLAN_RULES = """在正式撰写章节之前，先制定一份详细的写作规划。规划范围仅限当前章节，不得包含其他章节要点。

输出 JSON，结构如下：
{
  "key_points": ["必须覆盖的要点1", "要点2"],
  "technical_methods": ["拟采用的主要工艺/方法"],
  "data_to_include": ["需要包含的关键技术数据/参数"],
  "charts_needed": [{"type": "GANTT_DATA", "purpose": "用途说明"}],
  "word_count_target": 1200,
  "avoid": ["上一章已描述过的内容，本章不重复"],
  "retrieval_focus": ["用于二次检索的工艺/设备关键词"]
}

key_points 须覆盖本章每条评分项的「必备要素」（若有）及评分细则中的量化/管理要求；高分值项优先列入。"""


def get_plan_system_prompt(domain: str | None = None) -> str:
    domain = domain or DEFAULT_DOMAIN
    if domain == DEFAULT_DOMAIN:
        identity = "你是电力工程技术方案写作规划专家。"
    else:
        identity = f"你是{domain}技术方案写作规划专家，熟悉该领域施工组织与验收要求。"
    return f"{identity}\n{_PLAN_RULES}"


# 兼容旧引用
PLAN_SYSTEM_PROMPT = get_plan_system_prompt(DEFAULT_DOMAIN)

_OTHER_LEAF_PLAN_LIMIT = 40


def build_plan_user_prompt(bundle: dict) -> str:
    guidance = bundle.get("guidance") or {}
    target_words = guidance.get("target_words") or 1000
    type_hint = ""
    chapter_type = get_chapter_type(bundle.get("chapter_title"))
    constraints = get_chapter_constraints(bundle.get("chapter_title"))
    if constraints:
        type_hint = f"\n\n{constraints}"
        if chapter_type == "goal":
            type_hint += (
                "\n规划时 key_points 仅列目标承诺，technical_methods 留空或填「无」，"
                "data_to_include 仅保留总工期、合同价等宏观数据，charts_needed 留空。"
            )
        elif chapter_type == "overview":
            type_hint += (
                "\n规划时 key_points 仅列项目客观信息与特点，technical_methods 留空或填「无」，"
                "data_to_include 仅保留规模、电压等级、工期、地点等全局事实，charts_needed 留空。"
            )

    sibling_titles = bundle.get("sibling_leaf_titles") or []
    other_titles = bundle.get("other_leaf_titles") or []

    overview_block = format_overview_block(bundle.get("project_overview") or "", style="plan")
    facts_block = format_facts_block(bundle.get("global_facts_text") or "", style="plan")
    prior_block = format_prior_chapters_block(bundle, style="plan")
    contra_block = format_contradictions_block(bundle.get("contradictions") or [], style="plan")
    extras_block = format_generation_extras(bundle, style="plan")
    retrieval_notes = format_retrieval_notes(bundle, inline=False)
    req_hint = (bundle.get("requirements_hint") or "").strip()
    req_hint_block = f"\n\n{req_hint}" if req_hint else ""
    matrix_context = (bundle.get("matrix_context") or "").strip()
    matrix_block = f"\n\n## 本章评分响应矩阵\n{matrix_context}\n" if matrix_context else ""
    evaluation_focus = (bundle.get("evaluation_focus") or "").strip()
    focus_block = f"\n\n{evaluation_focus}\n" if evaluation_focus else ""

    return f"""## 全局工程信息
{json.dumps(bundle['global_params'], ensure_ascii=False, indent=2)}

{overview_block}## 本章评分项
{bundle['requirements_text']}{req_hint_block}{matrix_block}{focus_block}

## 检索素材
{bundle['retrieval_text'] or '（无检索素材）'}
{retrieval_notes}
{facts_block}{prior_block}{contra_block}## 章节定位
标题：{bundle['chapter_title']}
路径：{bundle['chapter_path']}
写作要点：{guidance.get('brief') or '无'}
内容边界：{guidance.get('content_boundary') or '无'}
建议篇幅约 {target_words} 字

## 范围约束（规划不得包含下列章节要点）
{format_scope_constraints(bundle, style="plan", limit=_OTHER_LEAF_PLAN_LIMIT)}
{type_hint}

{extras_block}请输出本章写作规划 JSON。"""

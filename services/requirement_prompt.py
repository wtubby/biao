"""评分项 → 提示词文本（plan / writer / qa 共用）。"""

from __future__ import annotations

from db.models import TechRequirement

_HIGH_SCORE_THRESHOLD = 8.0


def _format_meta_line(label: str, value: str | int | float | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return f"- {label}：{text}"


def format_requirement_block(req: TechRequirement) -> str:
    """单条评分项的结构化说明，供模型在规划/撰写时对齐响应。"""
    title = getattr(req, "requirement_title", None) or "未命名评分项"
    lines = [f"【{title}】"]

    score = getattr(req, "score_value", None)
    if score is not None and float(score) > 0:
        lines.append(f"- 分值：{score:g} 分")
        if float(score) >= _HIGH_SCORE_THRESHOLD:
            lines.append("- 篇幅要求：高分项，须写足工艺步骤、控制参数与可验证措施，避免空泛口号")

    if getattr(req, "is_risk_item", 0) == 1:
        lines.append("- 刚性：是（缺项或明显不响应将严重失分）")

    category = (getattr(req, "score_category", None) or "").strip()
    if category:
        lines.append(f"- 评分类别：{category}")

    keyword = (getattr(req, "keyword", None) or "").strip()
    if keyword:
        lines.append(f"- 评分关键词：{keyword}")

    mandatory = (getattr(req, "mandatory_elements", None) or "").strip()
    if mandatory:
        lines.append(f"- 必备要素（须在本章逐条体现）：{mandatory}")

    evidence = (getattr(req, "evidence_materials", None) or "").strip()
    if evidence:
        lines.append(f"- 建议证据/附图：{evidence}")

    risk_hint = (getattr(req, "risk_hint", None) or "").strip()
    if risk_hint:
        lines.append(f"- 风险提示：{risk_hint}")

    source = (getattr(req, "source_text", None) or "").strip()
    if source:
        lines.append("- 评分细则：")
        lines.append(source)
    elif len(lines) == 1:
        lines.append("- 评分细则：（无摘录原文）")

    return "\n".join(lines)


def format_requirements_text(requirements: list[TechRequirement]) -> str:
    if not requirements:
        return "（本章未绑定评分项）"
    return "\n\n".join(format_requirement_block(r) for r in requirements)


def requirements_response_hint(requirements: list[TechRequirement]) -> str:
    """章节级响应提醒，附在评分项块之后。"""
    if not requirements:
        return ""
    total = sum(float(getattr(r, "score_value", 0) or 0) for r in requirements)
    has_mandatory = any((getattr(r, "mandatory_elements", None) or "").strip() for r in requirements)
    has_risk = any(getattr(r, "is_risk_item", 0) == 1 for r in requirements)
    parts: list[str] = []
    if total > 0:
        parts.append(
            f"本章绑定评分项合计约 {total:g} 分；撰写须让评标专家能按上表逐条找到得分点。"
        )
    if has_mandatory:
        parts.append("凡标注「必备要素」者，须在正文中逐条体现，不得仅用「完全响应」一笔带过。")
    if has_risk:
        parts.append("刚性评分项不得遗漏或敷衍，须与全局工程事实一致。")
    if not parts:
        return ""
    return "【响应要求】\n" + "\n".join(f"- {p}" for p in parts)


_CHAPTER_FOCUS_PARAM_KEYS = ("工程名称", "电压等级", "总工期", "建设地点", "合同范围")


def build_chapter_evaluation_focus(
    chapter_title: str,
    requirements: list[TechRequirement],
    global_params: dict | None = None,
) -> str:
    """规则生成「本章评标关注点」，供 plan/writer 对齐高分响应。"""
    from services.writing_guidance import get_chapter_type, is_descriptive_chapter

    if is_descriptive_chapter(chapter_title) or not requirements:
        return ""

    lines = ["【本章评标关注点】"]
    sorted_reqs = sorted(
        requirements,
        key=lambda r: (
            -int(getattr(r, "is_risk_item", 0) or 0),
            -float(getattr(r, "score_value", 0) or 0),
        ),
    )
    for req in sorted_reqs[:6]:
        title = getattr(req, "requirement_title", None) or "评分项"
        score = float(getattr(req, "score_value", 0) or 0)
        prefix = "刚性" if getattr(req, "is_risk_item", 0) == 1 else f"{score:g}分"
        focus_parts: list[str] = []
        keyword = (getattr(req, "keyword", None) or "").strip()
        if keyword:
            focus_parts.append(f"关键词：{keyword}")
        mandatory = (getattr(req, "mandatory_elements", None) or "").strip()
        if mandatory:
            focus_parts.append(f"必备：{mandatory}")
        detail = "；".join(focus_parts) if focus_parts else "须实质性响应评分细则"
        lines.append(f"- [{prefix}] {title}：{detail}")

    if global_params:
        anchors = []
        for key in _CHAPTER_FOCUS_PARAM_KEYS:
            val = global_params.get(key)
            if val is not None and str(val).strip():
                anchors.append(f"{key}={val}")
        if anchors:
            lines.append(f"- 须贴合本项目：{'；'.join(anchors)}")

    if get_chapter_type(chapter_title) == "construction":
        lines.append("- 避免通稿套话；须出现与本章标题、工程量相关的具体表述")

    return "\n".join(lines) if len(lines) > 1 else ""


def maybe_refine_evaluation_focus(base_focus: str, bundle: dict) -> str:
    """可选：高分施工章用 LLM 将评标关注点压缩为更 actionable 的短列表。"""
    focus = (base_focus or "").strip()
    if not focus:
        return ""

    from config import EVALUATION_FOCUS_LLM_REFINE, EVALUATION_FOCUS_REFINE_MIN_SCORE
    from services.writing_guidance import is_descriptive_chapter

    if not EVALUATION_FOCUS_LLM_REFINE or is_descriptive_chapter(bundle.get("chapter_title")):
        return focus

    requirements = bundle.get("requirements") or []
    total_score = sum(float(getattr(r, "score_value", 0) or 0) for r in requirements)
    if total_score < EVALUATION_FOCUS_REFINE_MIN_SCORE:
        return focus

    try:
        from llm.llm_client import call_llm_text

        chapter_title = bundle.get("chapter_title") or "本章"
        prompt = (
            f"将下列评标关注点压缩为 3~5 条可执行要点（每条≤40字），"
            f"保留刚性项与必备要素，不增删评分项名称。\n"
            f"章节：{chapter_title}\n\n{focus}\n\n"
            "只输出列表，每条以 - 开头。"
        )
        refined = call_llm_text([{"role": "user", "content": prompt}], max_tokens=300)
        body = (refined or "").strip()
        if body and body.startswith("-"):
            return "【本章评标关注点】\n" + body
    except Exception:
        pass
    return focus

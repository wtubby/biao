"""各阶段提示词共用的上下文块（overview / 矛盾点 / 范围 / 生成附加项）。"""

from __future__ import annotations

from typing import Literal

from prompts.bundle_blocks import truncate_reference_bid

ContradictionStyle = Literal["plan", "writer", "qa"]
ExtrasStyle = Literal["plan", "writer", "qa"]


def format_title_list(
    titles: list[str],
    *,
    limit: int = 40,
    empty: str = "（无）",
) -> str:
    cleaned = [t for t in titles if t]
    if not cleaned:
        return empty
    shown = cleaned[:limit]
    text = "、".join(shown)
    if len(cleaned) > limit:
        text += f" 等共 {len(cleaned)} 章"
    return text


def format_overview_block(overview: str, *, style: ExtrasStyle = "writer") -> str:
    text = (overview or "").strip()
    if not text:
        return ""
    if style == "plan":
        return f"""## 项目概况（全书背景）
{text}

"""
    if style == "qa":
        return f"\n项目概况：\n{text}\n"
    return f"""## 项目概况（全书背景，各章涉及时必须与此一致，不得编造矛盾信息）
{text}

"""


def format_facts_block(facts_text: str, *, style: ExtrasStyle = "writer") -> str:
    text = (facts_text or "").strip()
    if not text:
        return ""
    if style == "plan":
        return f"""## 全局事实变量（规划涉及时必须沿用）
{text}

"""
    if style == "qa":
        return f"\n全局事实变量：\n{text}\n"
    return f"""## 全局事实变量（正文涉及时必须与此一致）
{text}

"""


def format_contradictions_block(
    contradictions: list,
    *,
    style: ContradictionStyle = "writer",
    max_items: int = 6,
) -> str:
    if not contradictions:
        return ""
    lines: list[str] = []
    for item in contradictions[:max_items]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('summary') or item.get('description') or item}")
        else:
            lines.append(f"- {item}")
    if style == "plan":
        return (
            "## 招标文件已知矛盾（规划须择一立场并全书统一，不得两面承诺）\n"
            + "\n".join(lines)
            + "\n\n"
        )
    if style == "qa":
        return "\n招标矛盾点（不得两面承诺）：\n" + "\n".join(lines) + "\n"
    return (
        "## 招标文件已知矛盾（择一立场并与全局事实一致，不得两面承诺）\n"
        + "\n".join(lines)
        + "\n\n"
    )


def format_generation_extras(bundle: dict, *, style: ExtrasStyle = "writer") -> str:
    extras: list[str] = []
    chart_hint = (bundle.get("chart_density_hint") or "").strip()
    if chart_hint:
        extras.append(
            f"图表要求：{chart_hint}" if style == "qa" else f"## 图表要求\n{chart_hint}"
        )
    standards_hint = (bundle.get("standards_hint") or "").strip()
    if standards_hint:
        extras.append(
            f"写作惯例提示：{standards_hint}"
            if style == "qa"
            else f"## 写作惯例提示（非标准条文原文）\n{standards_hint}"
        )
    ref_bid = (bundle.get("reference_bid_text") or "").strip()
    if ref_bid:
        snippet = truncate_reference_bid(ref_bid)
        if style == "plan":
            extras.append(
                "## 以标写标参考（仅作结构/风格参考，规划勿照抄）\n" + snippet
            )
        elif style == "qa":
            extras.append(f"以标写标参考（节选）：{snippet}")
        else:
            extras.append(f"## 以标写标参考（仅作结构/风格参考，勿照抄）\n{snippet}")
    elif bundle.get("reference_bid_miss"):
        miss = (
            "已启用以标写标，但本章未检索到相关参考片段，规划勿臆造参考内容，按评分项与工程参数正常规划。"
            if style == "plan"
            else "以标写标：已启用但本章无相关参考片段，正文不得臆造参考内容"
        )
        if style in ("plan", "writer"):
            extras.append(f"## 以标写标说明\n{miss}")
        else:
            extras.append(miss)
    blind_constraints = (bundle.get("blind_bid_constraints") or "").strip()
    if blind_constraints:
        extras.append(blind_constraints)
    if not extras:
        return ""
    parts = [part.strip() for part in extras if part.strip()]
    if style == "qa":
        return "\n" + "\n".join(parts) + "\n"
    return "\n\n".join(parts) + "\n\n"


def format_scope_constraints(
    bundle: dict,
    *,
    style: ExtrasStyle = "writer",
    limit: int = 40,
) -> str:
    sibling_titles = bundle.get("sibling_leaf_titles") or []
    other_titles = bundle.get("other_leaf_titles") or []
    non_sibling = [t for t in other_titles if t not in set(sibling_titles)]

    if style == "plan":
        return (
            f"- 同节兄弟：{format_title_list(sibling_titles, limit=limit)}\n"
            f"- 全书其他叶子：{format_title_list(non_sibling, limit=limit)}"
        )
    if style == "qa":
        hints: list[str] = []
        if sibling_titles:
            hints.append(f"同节兄弟章节（不得涉及）：{'、'.join(sibling_titles)}")
        if non_sibling:
            hints.append(
                f"全书其他叶子章节（不得涉及）："
                f"{format_title_list(non_sibling, limit=limit, empty='')}"
            )
        return "\n".join(hints)
    chapter_title = (bundle.get("chapter_title") or "").strip() or "当前章节"
    scope_lines = [
        f"- 仅撰写「{chapter_title}」正文，不要输出 # 标题行",
        "- 不得撰写其他叶子章节的内容，不得用其他章节标题作小节标题",
    ]
    if sibling_titles:
        scope_lines.append(f"- 同节兄弟章节（禁止涉及）：{'、'.join(sibling_titles)}")
    other_hint = format_title_list(non_sibling, limit=limit, empty="")
    if other_hint:
        scope_lines.append(f"- 全书其他叶子章节（禁止涉及）：{other_hint}")
    return "\n".join(scope_lines)

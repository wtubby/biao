"""各阶段提示词共用的 bundle 上下文块。"""

from __future__ import annotations

from typing import Literal

from services.reference_bid_service import REFERENCE_BID_CHAPTER_LIMIT

PriorStyle = Literal["writer", "plan", "qa"]


def format_prior_chapters_block(bundle: dict, *, style: PriorStyle = "writer") -> str:
    """前序章节避让信息：有 prior_summaries 时不再重复展示 last_summary。"""
    prior = bundle.get("prior_summaries") or []
    has_sibling_body = bool((bundle.get("immediate_prior_sibling_body") or "").strip())
    if has_sibling_body and not prior:
        return ""
    if has_sibling_body:
        last = ""
    else:
        last = (bundle.get("last_summary") or "").strip()

    if prior:
        if style == "plan":
            header = "## 前序章节摘要（avoid 必须据此列出勿重复点）\n"
        elif style == "qa":
            header = "前序章节摘要（不得大段复述）：\n"
        else:
            header = "## 前序章节已写要点（禁止重复展开，仅可引用结论）\n"
        lines = "\n".join(f"- {s}" for s in prior[:5])
        suffix = "\n" if style == "qa" else "\n\n"
        return header + lines + suffix

    if last:
        if style == "plan":
            return (
                "## 上一章技术摘要（avoid 字段须据此列出勿重复点）\n"
                f"{last}\n\n"
            )
        if style == "qa":
            return f"上一章技术摘要：\n{last}\n"
        return (
            "## 上一章技术摘要（已写内容，本章勿重复展开）\n"
            f"{last}\n\n"
        )

    if style == "plan":
        return (
            "## 上一章技术摘要（avoid 字段须据此列出勿重复点）\n"
            "（首章，无上一章摘要）\n\n"
        )
    if style == "qa":
        return ""
    return (
        "## 上一章技术摘要（已写内容，本章勿重复展开）\n"
        "（首章，无上一章摘要）\n\n"
    )


def format_immediate_prior_sibling_block(bundle: dict, *, style: PriorStyle = "writer") -> str:
    """紧邻上一同级叶子正文接力（独立生成节点连贯性）。"""
    if style != "writer":
        return ""
    title = (bundle.get("immediate_prior_sibling_title") or "").strip()
    body = (bundle.get("immediate_prior_sibling_body") or "").strip()
    if not title or not body:
        return ""
    chapter_title = (bundle.get("chapter_title") or "").strip()
    return f"""## 已知前情（紧邻上一同级小节）
上一小节「{title}」已生成正文如下（请直接承接，勿复读背景）：
----
{body}
----
## 当前连贯性要求
- 撰写本节「{chapter_title}」正文，须承接上文具体术语与结论（如施工段划分、资源配置名称）
- 严禁复读或重新引入上文已交代背景
- 段首直接写技术内容，禁止「综上所述」「接下来我们将」等过渡套话

"""


def format_retrieval_notes(bundle: dict, *, inline: bool = True) -> str:
    """合并无检索素材提示与领域降级警告。"""
    parts: list[str] = []
    empty_hint = (bundle.get("empty_retrieval_hint") or "").strip()
    if empty_hint:
        parts.append(empty_hint)
    warning = (bundle.get("retrieval_warning") or "").strip()
    if warning and warning not in parts:
        parts.append(warning)
    retrieval_text = (bundle.get("retrieval_text") or "").strip()
    if retrieval_text and retrieval_text != "（无检索素材）":
        parts.append("素材已标注来源；无来源标签的具体型号、品牌、标准号不得写入正文")
    if not parts:
        return ""
    text = "；".join(parts)
    if inline:
        return f"\n（检索说明：{text}）\n"
    return f"\n检索说明：\n{text}\n"


def truncate_reference_bid(text: str, *, limit: int = REFERENCE_BID_CHAPTER_LIMIT) -> str:
    """以标写标片段注入上限（与 reference_bid_service 一致）。"""
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit]

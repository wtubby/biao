"""大纲叶子 content_boundary 质量门禁。"""

from __future__ import annotations

from services.writing_guidance import (
    default_content_boundary_for_title,
    get_chapter_type,
    parse_writing_guidance,
    serialize_writing_guidance,
)

_GOAL_FORBIDDEN = ("措施", "保证", "方案", "计划", "组织", "方法", "工序", "检验频次", "工艺方法")
_OVERVIEW_FORBIDDEN = _GOAL_FORBIDDEN + (
    "我方将采取",
    "拟采用",
    "施工组织",
    "专项方案",
    "进度计划",
)
_CONSTRUCTION_HINTS = ("工序", "工艺", "控制", "要点", "参数", "质量", "安装", "调试", "验收", "措施")
_SPECIAL_TITLE_MARKERS = ("安装", "敷设", "调试", "专项", "施工方案")


def validate_content_boundary(title: str, boundary: str) -> list[str]:
    """校验叶子节点 content_boundary 是否符合章节类型约束。"""
    issues: list[str] = []
    text = (boundary or "").strip()
    if len(text) < 20:
        issues.append("content_boundary 过短（少于 20 字）")
    if len(text) > 200:
        issues.append("content_boundary 超过 200 字上限")

    chapter_type = get_chapter_type(title)
    if chapter_type == "goal":
        for kw in _GOAL_FORBIDDEN:
            if kw in text:
                issues.append(f"目标类章节 boundary 含禁止词「{kw}」")
    elif chapter_type == "overview":
        for kw in _OVERVIEW_FORBIDDEN:
            if kw in text:
                issues.append(f"概况类章节 boundary 含禁止词「{kw}」")
    elif any(marker in (title or "") for marker in _SPECIAL_TITLE_MARKERS):
        if not any(hint in text for hint in _CONSTRUCTION_HINTS):
            issues.append("专项/安装类章节 boundary 缺少工序或控制要点表述")

    return issues


def _leaf_boundary(node: dict) -> str:
    boundary = str(node.get("content_boundary") or "").strip()
    if boundary:
        return boundary
    wg_raw = node.get("writing_guidance")
    if isinstance(wg_raw, str) and wg_raw.strip():
        return parse_writing_guidance(wg_raw).get("content_boundary") or ""
    return ""


def sanitize_leaf_content_boundaries(nodes: list[dict]) -> tuple[list[dict], list[str]]:
    """修正不合格 boundary；返回新节点列表与用户可见警告。"""
    warnings: list[str] = []
    result: list[dict] = []

    for node in nodes:
        item = dict(node)
        if not item.get("is_leaf"):
            result.append(item)
            continue

        title = str(item.get("title") or "").strip() or "未命名章节"
        boundary = _leaf_boundary(item)
        issues = validate_content_boundary(title, boundary)
        if issues:
            fallback = default_content_boundary_for_title(title)
            if fallback:
                warnings.append(
                    f"章节「{title}」content_boundary 未通过校验（{'；'.join(issues)}），"
                    "已替换为类型默认边界"
                )
                boundary = fallback
            else:
                warnings.append(
                    f"章节「{title}」content_boundary 未通过校验（{'；'.join(issues)}），请人工检查"
                )

        item["content_boundary"] = boundary
        wg_raw = item.get("writing_guidance")
        parsed = (
            parse_writing_guidance(wg_raw)
            if isinstance(wg_raw, str) and wg_raw.strip().startswith("{")
            else None
        )
        brief = str(item.get("guidance_brief") or "").strip()
        if not brief:
            if parsed:
                brief = parsed.get("brief") or ""
            elif isinstance(wg_raw, str):
                brief = wg_raw.strip()
        target_words = item.get("target_words")
        if target_words is None and parsed:
            target_words = parsed.get("target_words")
        split_origin = bool(parsed.get("split_origin")) if parsed else False
        style_tier = item.get("style_tier") or (parsed.get("style_tier") if parsed else None)

        item["writing_guidance"] = serialize_writing_guidance(
            brief=brief,
            content_boundary=boundary,
            target_words=target_words,
            split_origin=split_origin,
            style_tier=style_tier,
        )
        result.append(item)

    return result, warnings

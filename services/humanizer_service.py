"""生成后轻量去痕：替换常见 AI 套话，保留电力专业术语。

词表单一来源：_AI_CLICHE_RULES。检测 / 替换 / 段首剥离均由此派生。
"""

from __future__ import annotations

import re
from typing import Any

from services.qa_rules import normalize_ai_spacing

# 统一套话规则：detect 全量扫描；replace/strip/filler 驱动 humanize
_AI_CLICHE_RULES: list[dict[str, Any]] = [
    {"phrase": "综上所述", "category": "总结套话", "suggestion": "改为对本节要点的直接概括", "strip": True},
    {"phrase": "总体而言", "category": "总结套话", "suggestion": "删去或写具体结论", "strip": True},
    {"phrase": "总的来说", "category": "总结套话", "suggestion": "删去或写具体结论", "strip": True},
    {"phrase": "总而言之", "category": "总结套话", "suggestion": "删去或写具体结论", "strip": True},
    {"phrase": "值得注意的是", "category": "过渡套话", "suggestion": "直接进入技术内容", "filler": True},
    {"phrase": "需要指出的是", "category": "过渡套话", "suggestion": "删去或改为具体说明", "filler": True},
    {"phrase": "不难发现", "category": "过渡套话", "suggestion": "删去", "filler": True},
    {"phrase": "众所周知", "category": "过渡套话", "suggestion": "删去", "filler": True},
    {"phrase": "显而易见", "category": "过渡套话", "suggestion": "删去", "filler": True},
    {"phrase": "毋庸置疑", "category": "过渡套话", "suggestion": "删去", "filler": True},
    {"phrase": "在当今社会", "category": "空泛开头", "suggestion": "删去，从工程背景写起", "strip": True},
    {"phrase": "随着时代的发展", "category": "空泛开头", "suggestion": "删去，从项目实际写起", "strip": True},
    {"phrase": "随着社会经济的发展", "category": "空泛开头", "suggestion": "删去，从项目实际写起", "strip": True},
    {"phrase": "具有重要意义", "category": "空泛评价", "suggestion": "写明对工程质量/工期/安全的具体作用"},
    {"phrase": "发挥重要作用", "category": "空泛评价", "suggestion": "写明具体作用对象与指标"},
    {"phrase": "全方位", "category": "夸张修饰", "suggestion": "改为具体范围或措施"},
    {"phrase": "多层次", "category": "夸张修饰", "suggestion": "写明具体层级或环节"},
    {"phrase": "深度融合", "category": "互联网套话", "suggestion": "改为具体结合方式"},
    {"phrase": "赋能", "category": "互联网套话", "suggestion": "改为支持/保障/提升", "replace": "支持"},
    {"phrase": "助力", "category": "互联网套话", "suggestion": "改为帮助/促进", "replace": "帮助"},
    {"phrase": "底层逻辑", "category": "互联网套话", "suggestion": "改为基本原理/主要原因", "replace": "基本原理"},
    {"phrase": "顶层设计", "category": "互联网套话", "suggestion": "改为总体方案/总体规划", "replace": "整体规划"},
    {"phrase": "闭环管理", "category": "互联网套话", "suggestion": "改为全过程管控"},
    {"phrase": "闭环", "category": "互联网套话", "suggestion": "改为全流程/全过程", "replace": "全流程"},
    {"phrase": "颗粒度", "category": "互联网套话", "suggestion": "改为细致程度/管理精度", "replace": "细致程度"},
    # 段首过渡（仅 humanize 剥离 + detect）；顺序连接词（首先/其次/最后等）不列入
    {"phrase": "不仅如此", "category": "段首套话", "suggestion": "段首过渡词可删去，直接写技术内容", "filler": True},
    {"phrase": "更重要的是", "category": "段首套话", "suggestion": "段首过渡词可删去，直接写技术内容", "filler": True},
]

_REPLACEMENTS = {
    rule["phrase"]: rule["replace"]
    for rule in _AI_CLICHE_RULES
    if rule.get("replace")
}

# 段首/句首剥离：带标点变体
_STRIP_LEADING_PHRASES: tuple[str, ...] = tuple(
    variant
    for rule in _AI_CLICHE_RULES
    if rule.get("strip")
    for variant in (f"{rule['phrase']}，", f"{rule['phrase']}。")
)

_FILLER_PREFIXES: tuple[str, ...] = tuple(
    f"{rule['phrase']}，"
    for rule in _AI_CLICHE_RULES
    if rule.get("filler")
)

_VARIATION_WORDS = {
    "采用": ("使用", "选用"),
    "实现": ("完成", "达到"),
    "确保": ("保证", "保障"),
}


def humanize_content(text: str, *, deep: bool = False) -> str:
    if not text or len(text) < 80:
        return text

    result = text
    for old, new in _REPLACEMENTS.items():
        result = result.replace(old, new)

    for phrase in _STRIP_LEADING_PHRASES:
        result = result.replace("\n" + phrase, "\n")
        if result.startswith(phrase):
            result = result[len(phrase) :]
        bare = phrase.rstrip("，。")
        result = result.replace(f"。{phrase}", "。")
        result = result.replace(f"。{bare}，", "。")
        result = result.replace(f"。{bare}。", "。")

    for phrase in _FILLER_PREFIXES:
        result = result.replace("\n" + phrase, "\n")
        if result.startswith(phrase):
            result = result[len(phrase) :]

    for word, alts in _VARIATION_WORDS.items():
        count = result.count(word)
        if count > 4:
            for i, alt in enumerate(alts):
                if i >= count - 3:
                    break
                result = result.replace(word, alt, 1)

    result = _split_long_sentences(result)
    result = normalize_ai_spacing(result)
    if deep:
        result = deep_humanize_content(result)
    return result


def deep_humanize_content(text: str) -> str:
    """可选深度去痕：对高密度套话段落做 LLM 轻量改写；失败则回退原文。"""
    if not text or len(text) < 200:
        return text
    hits = detect_ai_cliches(text)
    if len(hits) < 3:
        return text
    try:
        from llm.llm_client import call_llm_text

        prompt = (
            "请改写以下技术方案段落，去掉空泛套话与互联网用语，"
            "保留全部技术参数、工序、标准号与 Markdown/图表占位符，"
            "不要增加公司名称或联系方式。只输出改写后正文。\n\n"
            f"{text[:6000]}"
        )
        rewritten = call_llm_text(
            [
                {"role": "system", "content": "你是技术方案润色编辑，擅长去 AI 痕迹。"},
                {"role": "user", "content": prompt},
            ],
            role="writer",
        )
        cleaned = (rewritten or "").strip()
        if len(cleaned) < max(80, int(len(text) * 0.4)):
            return text
        return normalize_ai_spacing(cleaned)
    except Exception:
        return text


def detect_ai_cliches(text: str) -> list[dict[str, Any]]:
    """检测正文中的疑似 AI 套话，返回命中位置与改写建议。"""
    if not text:
        return []

    hits: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    def _add_hit(phrase: str, start: int, end: int, category: str, suggestion: str) -> None:
        span = (start, end)
        if span in seen_spans:
            return
        seen_spans.add(span)
        hits.append(
            {
                "phrase": phrase,
                "start": start,
                "end": end,
                "category": category,
                "suggestion": suggestion,
            }
        )

    for rule in _AI_CLICHE_RULES:
        phrase = rule["phrase"]
        # 段首过渡词仅匹配「词+逗号」，避免误伤「首先进行验收」等正常表述
        search = f"{phrase}，" if rule.get("filler") else phrase
        report_phrase = phrase
        start = 0
        while True:
            idx = text.find(search, start)
            if idx < 0:
                break
            _add_hit(
                report_phrase,
                idx,
                idx + len(search) if rule.get("filler") else idx + len(phrase),
                rule.get("category", "套话"),
                rule.get("suggestion", ""),
            )
            start = idx + len(search)

    hits.sort(key=lambda item: item["start"])
    return hits


def _split_long_sentences(text: str) -> str:
    parts: list[str] = []
    for block in text.split("\n\n"):
        sentences = re.split(r"(?<=[。；])", block)
        rebuilt: list[str] = []
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            if len(s) > 120 and "，" in s:
                comma_parts = s.split("，")
                if len(comma_parts) > 2:
                    mid = len(comma_parts) // 2
                    s = "，".join(comma_parts[:mid]) + "。\n" + "，".join(comma_parts[mid:])
            rebuilt.append(s)
        parts.append("".join(rebuilt))
    return "\n\n".join(parts)

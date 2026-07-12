"""写作指导字段解析与章节类型路由（概况/目标 vs 方案/措施）。"""

import json
from typing import Any, Literal

ChapterType = Literal["goal", "overview", "construction"]

# 目标类：只写承诺，不写措施
_GOAL_EXCLUDE_KEYWORDS = ("措施", "保证", "方案", "计划", "组织", "方法")
_GOAL_MARKERS = (
    "项目目标",
    "质量目标",
    "工期目标",
    "进度目标",
    "造价目标",
    "成本目标",
    "安全目标",
    "文明施工目标",
)
_GOAL_TOPIC_KEYWORDS = ("质量", "工期", "进度", "造价", "成本", "安全", "文明")

# 概况/特点类：只描述项目客观事实与特征，不写方案措施（商用标书「先概况、后方案」范式）
_OVERVIEW_EXCLUDE_KEYWORDS = _GOAL_EXCLUDE_KEYWORDS + ("应对", "对策", "解决")
_OVERVIEW_MARKERS = (
    "项目特点",
    "工程特点",
    "工程概况",
    "项目概况",
    "项目背景",
    "建设规模",
    "工程简介",
    "项目简介",
    "工程规模",
    "现场条件",
    "施工条件",
    "自然环境",
    "社会环境",
)

GOAL_CHAPTER_CONSTRAINTS = """【本章为项目目标类章节，以下约束优先于通用写作规范】
- 只写目标承诺：质量、工期、造价（成本）等各用 1~3 条概括性表述即可
- 禁止写实现措施：不得出现组织机构、施工步骤、检验频次、工艺方法、资源配置等保证措施内容
- 目标宜粗不宜细：用「合格」「一次投运成功」「不超合同价」「按期竣工」等原则性承诺；不写工序、设备型号、检测参数等细节
- 不要采用「目标 + 措施」结构；每条目标 1~2 句话，篇幅宜短，避免展开论述"""

OVERVIEW_CHAPTER_CONSTRAINTS = """【本章为工程概况/项目特点类章节，以下约束优先于通用写作规范】
- 只描述项目客观事实与特征：建设规模、电压等级、主要设备数量、建设地点、地形地貌、交通、周边环境、合同范围等
- 可归纳本工程有别于常规项目的显著特点，可点出施工重难点（仅描述现象与成因），但不展开对策
- 禁止写施工组织、质量保证措施、专项施工方案、进度计划、资源配置、管理体系等后续章节内容
- 禁止「针对上述特点/难点，我方将采取…」「拟采用…方案」等对策句式；不写工序步骤与检验频次
- 以陈述句为主，篇幅适中；本节为后续技术方案章节的背景依据，不预写方案正文"""

_CHAPTER_CONSTRAINTS: dict[ChapterType, str] = {
    "goal": GOAL_CHAPTER_CONSTRAINTS,
    "overview": OVERVIEW_CHAPTER_CONSTRAINTS,
}


def is_goal_chapter(title: str | None) -> bool:
    return get_chapter_type(title) == "goal"


def is_overview_chapter(title: str | None) -> bool:
    return get_chapter_type(title) == "overview"


def is_descriptive_chapter(title: str | None) -> bool:
    """概况/特点/目标类：描述事实或承诺，不写方案措施。"""
    return get_chapter_type(title) in ("goal", "overview")


def should_skip_content_plan(bundle: dict, *, word_threshold: int = 500) -> bool:
    """描述类或低分短章跳过 LLM 写作规划。"""
    title = bundle.get("chapter_title") or ""
    if is_descriptive_chapter(title):
        return True
    guidance = bundle.get("guidance") or {}
    target_words = int(guidance.get("target_words") or 0)
    if target_words > 0 and target_words < word_threshold:
        return True
    return False


def get_chapter_type(title: str | None) -> ChapterType:
    t = (title or "").strip()
    if not t:
        return "construction"

    if _match_goal(t):
        return "goal"
    if _match_overview(t):
        return "overview"
    return "construction"


def get_chapter_constraints(title: str | None) -> str | None:
    return _CHAPTER_CONSTRAINTS.get(get_chapter_type(title))


def _match_goal(t: str) -> bool:
    if "目标" not in t:
        return False
    if any(k in t for k in _GOAL_EXCLUDE_KEYWORDS):
        return False
    if any(m in t for m in _GOAL_MARKERS):
        return True
    return any(k in t for k in _GOAL_TOPIC_KEYWORDS)


def _match_overview(t: str) -> bool:
    if any(k in t for k in _OVERVIEW_EXCLUDE_KEYWORDS):
        return False
    if any(m in t for m in _OVERVIEW_MARKERS):
        return True
    if "概况" in t or "简介" in t:
        return True
    if "特点" in t and not any(k in t for k in ("技术特点", "性能特点")):
        # 「设备技术特点」等偏技术参数，不归入概况类
        if any(k in t for k in ("项目", "工程", "施工")):
            return True
    return False


def _empty_guidance() -> dict[str, Any]:
    return {
        "brief": "",
        "content_boundary": "",
        "target_words": None,
        "split_origin": False,
    }


def parse_writing_guidance(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return _empty_guidance()

    text = str(raw).strip()
    if not text.startswith("{"):
        return _empty_guidance()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {
                "brief": str(data.get("brief") or "").strip(),
                "content_boundary": str(data.get("content_boundary") or "").strip(),
                "target_words": _coerce_int(data.get("target_words")),
                "split_origin": bool(data.get("split_origin")),
            }
    except json.JSONDecodeError:
        pass

    return _empty_guidance()


def serialize_writing_guidance(
    brief: str = "",
    content_boundary: str = "",
    target_words: int | None = None,
    split_origin: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "brief": (brief or "").strip(),
        "content_boundary": (content_boundary or "").strip(),
    }
    if target_words is not None and target_words > 0:
        payload["target_words"] = int(target_words)
    if split_origin:
        payload["split_origin"] = True
    return json.dumps(payload, ensure_ascii=False)


def guidance_to_outline_dict(raw: str | None) -> dict[str, Any]:
    parsed = parse_writing_guidance(raw)
    return {
        "writing_guidance": raw,
        "guidance_brief": parsed["brief"],
        "content_boundary": parsed["content_boundary"],
        "target_words": parsed["target_words"],
        "split_origin": parsed["split_origin"],
    }


def default_content_boundary_for_title(title: str) -> str | None:
    """按章节类型返回默认内容边界（无 AI 深化时的兜底）。"""
    chapter_type = get_chapter_type(title)
    if chapter_type == "goal":
        return (
            f"仅撰写「{title}」的目标承诺（质量、工期、造价等概括性表述），"
            "不写保证措施、施工方案或工艺细节；不输出章节标题行。"
        )
    if chapter_type == "overview":
        return (
            f"仅撰写「{title}」的客观描述（规模、地点、设备、环境、工程特点等），"
            "可描述重难点现象但不写对策；不写施工方案、组织、措施或进度计划；不输出章节标题行。"
        )
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        num = int(value)
        return num if num > 0 else None
    except (TypeError, ValueError):
        return None

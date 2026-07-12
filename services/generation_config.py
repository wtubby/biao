"""生成前配置：图表密度、知识库、以标写标、规范库、生成档位等。"""

from __future__ import annotations

from typing import Any

from db.models import Project
from domains.registry import DEFAULT_DOMAIN
from services.project_meta import get_meta, set_meta

TARGET_PAGES_MIN = 10
TARGET_PAGES_MAX = 1200

GENERATION_MODE_FULL = "full"
GENERATION_MODE_COMPACT = "compact"
GENERATION_MODES = (GENERATION_MODE_FULL, GENERATION_MODE_COMPACT)

COMPACT_TARGET_WORDS_FACTOR = 0.6
COMPACT_MIN_TARGET_WORDS = 200

CHART_DENSITY_NONE = "none"
CHART_DENSITY_NORMAL = "normal"
CHART_DENSITY_ABUNDANT = "abundant"
CHART_DENSITIES = (CHART_DENSITY_NONE, CHART_DENSITY_NORMAL, CHART_DENSITY_ABUNDANT)

STANDARDS_PACK_NONE = "none"
STANDARDS_PACK_EPC = "epc_guide"
STANDARDS_PACKS = (STANDARDS_PACK_NONE, STANDARDS_PACK_EPC)

_CONFIG_KEYS = (
    "chart_density",
    "use_knowledge_library",
    "reference_bid_enabled",
    "reference_bid_text",
    "reference_bid_filename",
    "standards_pack",
    "custom_word_count",
    "custom_total_words",
    "format_confirmed_at",
    "require_risk_binding",
    "deep_humanize",
)


def default_generation_config(domain: str | None = None) -> dict[str, Any]:
    default_pack = (
        STANDARDS_PACK_EPC if (domain or DEFAULT_DOMAIN) == DEFAULT_DOMAIN else STANDARDS_PACK_NONE
    )
    return {
        "chart_density": CHART_DENSITY_NORMAL,
        "use_knowledge_library": True,
        "reference_bid_enabled": False,
        "reference_bid_text": "",
        "reference_bid_filename": "",
        "standards_pack": default_pack,
        "custom_word_count": False,
        "custom_total_words": None,
        "format_confirmed_at": None,
        "require_risk_binding": True,
        "deep_humanize": False,
    }


def get_generation_config(project: Project) -> dict[str, Any]:
    domain = get_meta(project).get("engineering_domain")
    base = default_generation_config(domain)
    raw = get_meta(project).get("generation_config")
    if isinstance(raw, dict):
        for key in _CONFIG_KEYS:
            if key in raw:
                base[key] = raw[key]
    if base["chart_density"] not in CHART_DENSITIES:
        base["chart_density"] = CHART_DENSITY_NORMAL
    if base["standards_pack"] not in STANDARDS_PACKS:
        base["standards_pack"] = default_generation_config(domain)["standards_pack"]
    return base


def update_generation_config(project: Project, **kwargs: Any) -> dict[str, Any]:
    config = get_generation_config(project)
    for key, value in kwargs.items():
        if key not in _CONFIG_KEYS:
            continue
        if key == "chart_density" and value not in CHART_DENSITIES:
            raise ValueError("无效的图表程度")
        if key == "standards_pack" and value not in STANDARDS_PACKS:
            raise ValueError("无效的规范库选项")
        config[key] = value
    set_meta(project, generation_config=config)
    return config


def chart_density_hint(density: str) -> str:
    if density == CHART_DENSITY_NONE:
        return "本章尽量不插入图表占位符，以文字论述为主。"
    if density == CHART_DENSITY_ABUNDANT:
        return (
            "在合适位置多使用图表占位符（甘特图、流程图、组织架构图、表格等），"
            "每章建议至少 1~2 处 [GANTT_DATA]、[FLOW_DATA]、[ORG_DATA] 或 Markdown 表格。"
        )
    return "在关键工序、进度安排、组织架构等处适度插入 0~2 个图表占位符，避免堆砌。"


def standards_pack_hint(
    pack: str,
    *,
    chapter_title: str = "",
    brief: str = "",
    boundary: str = "",
) -> str:
    from services.standards_pack import build_standards_hint

    return build_standards_hint(
        pack,
        chapter_title=chapter_title,
        brief=brief,
        boundary=boundary,
    )


def get_generation_mode(project: Project) -> str:
    mode = str(get_meta(project).get("generation_mode") or "").strip()
    if mode in GENERATION_MODES:
        return mode
    return GENERATION_MODE_FULL


def set_generation_mode(project: Project, mode: str) -> None:
    if mode not in GENERATION_MODES:
        raise ValueError("无效的生成档位")
    set_meta(project, generation_mode=mode)


def is_compact_mode(mode: str) -> bool:
    return mode == GENERATION_MODE_COMPACT


def target_words_multiplier(mode: str) -> float:
    return COMPACT_TARGET_WORDS_FACTOR if is_compact_mode(mode) else 1.0


def scale_target_words(base_words: int | None, mode: str) -> int | None:
    if not base_words or base_words <= 0:
        return base_words
    scaled = int(round(base_words * target_words_multiplier(mode)))
    if is_compact_mode(mode):
        return max(COMPACT_MIN_TARGET_WORDS, scaled)
    return scaled


def skeleton_mode_hint(mode: str) -> str:
    if is_compact_mode(mode):
        return (
            "【精简版】每个一级章节下最多补充 2~3 个二级子节，倾向合并相近专业内容，"
            "避免过细拆分。"
        )
    return (
        "【满血版】对每个一级章节可按专业逻辑补充 2~6 个二级子节，结构完整、便于充分展开。"
    )


def branch_mode_hint(mode: str) -> str:
    if is_compact_mode(mode):
        return (
            "【精简版】优先将本分支作为单一叶子节点，不向下拆分；"
            "若多项评分项必须覆盖，最多拆到三级且本分支下叶子总数不超过 3；"
            "content_boundary 控制在 80~120 字。"
        )
    return (
        "【满血版】按专业逻辑正常拆分；content_boundary 控制在 80~200 字。"
    )


def mode_label(mode: str) -> str:
    return "精简版" if is_compact_mode(mode) else "满血版"

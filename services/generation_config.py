"""生成前配置：图表密度、知识库、以标写标、规范库、生成档位等。"""

from __future__ import annotations

from typing import Any

from db.models import Project
from domains.registry import DEFAULT_DOMAIN
from services.project_meta import get_meta, set_meta

TARGET_PAGES_MIN = 10
TARGET_PAGES_MAX = 1200
CUSTOM_TOTAL_WORDS_MIN = 3000
CUSTOM_TOTAL_WORDS_MAX = 500000


def normalize_target_pages(value: Any) -> int | None:
    """将 target_pages 解析并钳制到 [TARGET_PAGES_MIN, TARGET_PAGES_MAX]；非法则返回 None。"""
    if value is None or value == "":
        return None
    try:
        pages = int(value)
    except (TypeError, ValueError):
        return None
    return max(TARGET_PAGES_MIN, min(TARGET_PAGES_MAX, pages))


def normalize_custom_total_words(value: Any) -> int | None:
    """将 custom_total_words 解析并钳制到合法区间；非法则返回 None。"""
    if value is None or value == "":
        return None
    try:
        words = int(value)
    except (TypeError, ValueError):
        return None
    return max(CUSTOM_TOTAL_WORDS_MIN, min(CUSTOM_TOTAL_WORDS_MAX, words))


def resolve_target_pages(value: Any, *, default: int) -> int:
    """读取/使用 target_pages 时的安全解析，避免脏数据抬高全书篇幅。"""
    pages = normalize_target_pages(value)
    return pages if pages is not None else int(default)

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

BID_CATEGORY_SERVICE_PLAN = "service_plan"
BID_CATEGORY_PROCUREMENT = "procurement_goods"
BID_CATEGORY_ENGINEERING_TECH = "engineering_tech"
BID_CATEGORY_CONSTRUCTION_ORG = "construction_org"
BID_CATEGORY_HAZARDOUS_WORK = "hazardous_work"
BID_CATEGORIES = (
    BID_CATEGORY_SERVICE_PLAN,
    BID_CATEGORY_PROCUREMENT,
    BID_CATEGORY_ENGINEERING_TECH,
    BID_CATEGORY_CONSTRUCTION_ORG,
    BID_CATEGORY_HAZARDOUS_WORK,
)

_LEGACY_BID_CATEGORY_MAP = {
    "procurement": BID_CATEGORY_PROCUREMENT,
    "engineering": BID_CATEGORY_ENGINEERING_TECH,
    "service": BID_CATEGORY_SERVICE_PLAN,
}

BID_CATEGORY_LABELS: dict[str, str] = {
    BID_CATEGORY_SERVICE_PLAN: "服务方案",
    BID_CATEGORY_PROCUREMENT: "采购物资",
    BID_CATEGORY_ENGINEERING_TECH: "工程技术标",
    BID_CATEGORY_CONSTRUCTION_ORG: "施工组织设计",
    BID_CATEGORY_HAZARDOUS_WORK: "危大工程方案",
}

BID_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    BID_CATEGORY_SERVICE_PLAN: "物业、审计、物流等服务方案生成",
    BID_CATEGORY_PROCUREMENT: "物资、设备、软件等采购方案生成",
    BID_CATEGORY_ENGINEERING_TECH: "消防、市政、装修等工程方案生成",
    BID_CATEGORY_CONSTRUCTION_ORG: "全周期、专业级、可落地的合规方案生成",
    BID_CATEGORY_HAZARDOUS_WORK: "分部分项危大方案、安全管理、风险管控一体",
}

BODY_FORMAT_GENERAL = "general"
BODY_FORMAT_HEADING = "heading_hierarchy"
BODY_FORMAT_LIST = "list_items"
BODY_FORMATS = (BODY_FORMAT_GENERAL, BODY_FORMAT_HEADING, BODY_FORMAT_LIST)

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
    "bid_category",
    "body_format",
    "smartart_enabled",
    "typesetting",
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
        "bid_category": BID_CATEGORY_ENGINEERING_TECH,
        "body_format": BODY_FORMAT_GENERAL,
        "smartart_enabled": False,
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
    legacy_cat = base.get("bid_category")
    if isinstance(legacy_cat, str) and legacy_cat in _LEGACY_BID_CATEGORY_MAP:
        base["bid_category"] = _LEGACY_BID_CATEGORY_MAP[legacy_cat]
    if base["bid_category"] not in BID_CATEGORIES:
        base["bid_category"] = BID_CATEGORY_ENGINEERING_TECH
    if base["body_format"] not in BODY_FORMATS:
        base["body_format"] = BODY_FORMAT_GENERAL
    base["smartart_enabled"] = bool(base.get("smartart_enabled"))
    from services.typesetting_config import default_typesetting, normalize_typesetting

    base["typesetting"] = normalize_typesetting(
        base.get("typesetting") if isinstance(base.get("typesetting"), dict) else default_typesetting()
    )
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
        if key == "bid_category" and value not in BID_CATEGORIES:
            raise ValueError("无效的方案类型")
        if key == "body_format" and value not in BODY_FORMATS:
            raise ValueError("无效的正文格式")
        if key == "smartart_enabled":
            value = bool(value)
        if key == "typesetting":
            from services.typesetting_config import normalize_typesetting

            config[key] = normalize_typesetting(value)
            continue
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


def list_bid_category_options() -> list[dict[str, str]]:
    return [
        {
            "value": key,
            "label": BID_CATEGORY_LABELS[key],
            "description": BID_CATEGORY_DESCRIPTIONS[key],
        }
        for key in BID_CATEGORIES
    ]


def bid_category_hint(category: str) -> str:
    category = _LEGACY_BID_CATEGORY_MAP.get(category, category)
    if category == BID_CATEGORY_SERVICE_PLAN:
        return (
            "本项目为服务方案：侧重服务范围、人员配置、响应机制、质量保障与持续改进，"
            "突出可执行的服务流程与 SLA，避免写成施工组织设计口吻。"
        )
    if category == BID_CATEGORY_PROCUREMENT:
        return (
            "本项目为采购物资方案：侧重供货范围、技术参数响应、验收标准、售后服务与交付计划，"
            "参数须可核对，避免虚构品牌型号。"
        )
    if category == BID_CATEGORY_CONSTRUCTION_ORG:
        return (
            "本项目为施工组织设计：侧重总体部署、进度计划、资源配置、质量安全与文明施工，"
            "工序衔接与现场平面布置须可落地。"
        )
    if category == BID_CATEGORY_HAZARDOUS_WORK:
        return (
            "本项目为危大工程专项方案：侧重分部分项辨识、施工工艺、安全管控、监测预警与应急预案，"
            "须符合危大工程管理规定，措施具体可执行。"
        )
    return (
        "本项目为工程技术标：侧重施工/安装/调试技术路线、关键工序、质量安全与进度控制，"
        "参数与措施须可落地。"
    )


def body_format_hint(body_format: str) -> str:
    if body_format == BODY_FORMAT_HEADING:
        return (
            "正文用小标题分段（可用 **加粗短标题** 起段，严禁 # 号标题行），"
            "每小节 2~4 句展开，层次清晰。"
        )
    if body_format == BODY_FORMAT_LIST:
        return (
            "正文优先用 Markdown 有序/无序列表呈现要点，每条须有实质内容（步骤、参数或措施）；"
            "段首导语可 1~2 句，避免大段空泛叙述。"
        )
    return "正文以连贯段落论述为主，列表仅在枚举要点时适度使用。"


def smartart_hint(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        "本章鼓励插入 SmartArt 风格可视化占位符："
        "[ORG_DATA: {...}] 组织架构、[FLOW_DATA: [...]] 流程步骤、"
        "[SMART_DATA: [{\"title\":\"\",\"desc\":\"\"},...]] 对照说明表；"
        "导出时渲染为图片/表格（非 Word 原生 SmartArt 对象）。"
    )


def build_generation_hints(gen_config: dict[str, Any]) -> dict[str, str]:
    """汇总生成配置相关的提示词片段。"""
    density = gen_config.get("chart_density") or CHART_DENSITY_NORMAL
    chart_parts = [chart_density_hint(density)]
    smart = smartart_hint(bool(gen_config.get("smartart_enabled")))
    if smart:
        chart_parts.append(smart)
    return {
        "bid_category_hint": bid_category_hint(
            gen_config.get("bid_category") or BID_CATEGORY_ENGINEERING_TECH
        ),
        "body_format_hint": body_format_hint(
            gen_config.get("body_format") or BODY_FORMAT_GENERAL
        ),
        "chart_density_hint": "\n".join(chart_parts),
    }


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

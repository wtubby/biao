"""轻量规范/写作惯例条目包：按章节关键词注入相关提示。"""

from __future__ import annotations

# 每条：keywords 命中标题/要点时注入 clause（非完整标准条文，仅为写作约束提示）
_EPC_GUIDE_ENTRIES: list[dict[str, object]] = [
    {
        "keywords": ("概况", "概述", "项目特点", "工程概况", "项目简介"),
        "clause": "概况类：只写客观事实与特点，不写施工措施、保证承诺与「我方将采取」。",
    },
    {
        "keywords": ("目标", "质量目标", "工期目标", "造价目标"),
        "clause": "目标类：写可核验的承诺指标与验收口径，不展开具体施工工艺。",
    },
    {
        "keywords": ("进度", "工期", "网络计划", "横道", "里程碑"),
        "clause": "进度类：给出关键节点、逻辑关系与可量化工期；宜用甘特/里程碑占位，忌空泛「尽快完成」。",
    },
    {
        "keywords": ("施工", "安装", "方案", "工艺", "工序", "吊装", "调试", "试验"),
        "clause": "施工/方案类：步骤可执行、参数带单位，关键参数用 **[参数] 数值+单位**；引用标准号须来自检索素材或全局事实。",
    },
    {
        "keywords": ("质量", "质检", "验收", "检验"),
        "clause": "质量类：写控制点、检验批/见证取样逻辑与不合格处置，避免口号式「确保优质」。",
    },
    {
        "keywords": ("安全", "文明", "应急", "消防"),
        "clause": "安全类：写危险源、防护措施、应急响应与责任分工，指标可量化。",
    },
    {
        "keywords": ("环境", "环保", "职业健康", "扬尘", "噪声"),
        "clause": "环境/职业健康类：写污染因子、控制措施与监测频次，避免与安全章简单重复。",
    },
    {
        "keywords": ("采购", "分包", "供货", "设备"),
        "clause": "采购/分包类：写选型原则、供货计划、进场验收与接口界面，不编造未提供的品牌型号。",
    },
    {
        "keywords": ("组织", "机构", "人员", "岗位", "职责"),
        "clause": "组织机构类：写岗位设置、职责界面与汇报关系，可用组织架构图占位。",
    },
    {
        "keywords": ("设计", "勘察", "图纸", "深化设计"),
        "clause": "设计类：写设计依据、接口与成果交付，不编造未提供的图号与标准号。",
    },
    {
        "keywords": ("试验", "调试", "送电", "投运"),
        "clause": "试验/调试类：写试验项目、合格判据与安全措施；标准号须有来源。",
    },
]


def match_standards_clauses(
    pack: str,
    *,
    chapter_title: str = "",
    brief: str = "",
    boundary: str = "",
    max_items: int = 4,
) -> list[str]:
    if pack != "epc_guide":
        return []
    haystack = f"{chapter_title} {brief} {boundary}"
    matched: list[str] = []
    for entry in _EPC_GUIDE_ENTRIES:
        keywords = entry["keywords"]  # type: ignore[assignment]
        clause = str(entry["clause"])
        if any(kw in haystack for kw in keywords):  # type: ignore[arg-type]
            matched.append(clause)
        if len(matched) >= max_items:
            break
    return matched


def build_standards_hint(
    pack: str,
    *,
    chapter_title: str = "",
    brief: str = "",
    boundary: str = "",
) -> str:
    if pack == "none" or not pack:
        return ""
    if pack != "epc_guide":
        return ""

    base = (
        "写作惯例（非完整标准条文库）：符合电力 EPC 技术标表述习惯；"
        "引用规范/标准号时，仅可使用检索素材或全局事实中已出现的编号，禁止编造。"
    )
    clauses = match_standards_clauses(
        pack,
        chapter_title=chapter_title,
        brief=brief,
        boundary=boundary,
    )
    if not clauses:
        return base
    lines = "\n".join(f"- {c}" for c in clauses)
    return f"{base}\n本章相关提示：\n{lines}"

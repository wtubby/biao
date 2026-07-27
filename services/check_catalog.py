"""投标检查分类目录（借鉴 BidMaster-Pro 合规清单，按技术标场景裁剪）。"""

from __future__ import annotations

from typing import Any

# severity: info | warn | block
# scope: chapter | segment | project
CHECK_CATEGORIES: dict[str, dict[str, Any]] = {
    "template_residue": {
        "label": "模板残留",
        "default_severity": "block",
        "scope": ("chapter", "segment", "project"),
        "description": "未替换占位符、示例文本等废标高风险残留",
    },
    "blind_bid": {
        "label": "暗标合规",
        "default_severity": "block",
        "scope": ("chapter",),
        "description": "暗标模式下的身份信息泄露",
    },
    "mandatory_coverage": {
        "label": "必备要素",
        "default_severity": "warn",
        "scope": ("chapter", "project"),
        "description": "评分项 mandatory_elements 覆盖",
    },
    "scoring_coverage": {
        "label": "评分项覆盖",
        "default_severity": "block",
        "scope": ("chapter", "project"),
        "description": "评分项标题/关键词是否被正文响应",
    },
    "substantial_response": {
        "label": "实质性响应",
        "default_severity": "warn",
        "scope": ("chapter", "project"),
        "description": "★/▲/刚性条款附近的实质性响应表述",
    },
    "disqualification_risk": {
        "label": "废标条款",
        "default_severity": "warn",
        "scope": ("project",),
        "description": "招标文件废标项与正文风险对照",
    },
    "scope": {
        "label": "章节范围",
        "default_severity": "warn",
        "scope": ("chapter", "segment"),
        "description": "正文越界写到其他叶子章节",
    },
    "fact_consistency": {
        "label": "事实一致性",
        "default_severity": "warn",
        "scope": ("chapter", "project"),
        "description": "工期/地点/数量等与全局事实冲突",
    },
    "cross_chapter": {
        "label": "跨章重复",
        "default_severity": "warn",
        "scope": ("chapter",),
        "description": "与已写章节内容高度重复",
    },
    "fabricated_standards": {
        "label": "编造规范",
        "default_severity": "block",
        "scope": ("chapter", "segment"),
        "description": "疑似虚构标准号",
    },
    "truncation": {
        "label": "截断风险",
        "default_severity": "warn",
        "scope": ("chapter",),
        "description": "正文疑似生成截断",
    },
    "chart_integrity": {
        "label": "图表完整性",
        "default_severity": "warn",
        "scope": ("chapter", "segment"),
        "description": "图表占位符未闭合或不可渲染",
    },
    "table_integrity": {
        "label": "表格完整性",
        "default_severity": "warn",
        "scope": ("chapter", "segment"),
        "description": "Markdown 表格结构损坏",
    },
    "ai_cliche": {
        "label": "AI 套话",
        "default_severity": "warn",
        "scope": ("chapter",),
        "description": "空泛套话与 AI 痕迹",
    },
    "writing_quality": {
        "label": "写作质量",
        "default_severity": "warn",
        "scope": ("chapter",),
        "description": "首段复读、句式套路、概况章写措施等",
    },
    "word_count": {
        "label": "篇幅控制",
        "default_severity": "warn",
        "scope": ("chapter",),
        "description": "相对目标字数过短或过长",
    },
    "digit_density": {
        "label": "技术密度",
        "default_severity": "warn",
        "scope": ("chapter",),
        "description": "技术参数与数字密度不足",
    },
    "plan_coverage": {
        "label": "规划要点",
        "default_severity": "warn",
        "scope": ("chapter", "segment"),
        "description": "content_plan key_points 覆盖不足",
    },
    "title_keywords": {
        "label": "标题关键词",
        "default_severity": "warn",
        "scope": ("chapter", "project"),
        "description": "大纲/标题未覆盖评分关键词",
    },
    "font_safety": {
        "label": "字体规范",
        "default_severity": "warn",
        "scope": ("project",),
        "description": "导出文档字体是否安全",
    },
    "length_balance": {
        "label": "篇幅分布",
        "default_severity": "warn",
        "scope": ("project",),
        "description": "单章占全文比例过高",
    },
}


def category_label(category: str) -> str:
    meta = CHECK_CATEGORIES.get(category) or {}
    return str(meta.get("label") or category)


def category_default_severity(category: str) -> str:
    meta = CHECK_CATEGORIES.get(category) or {}
    return str(meta.get("default_severity") or "warn")


def list_categories(*, scope: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, meta in CHECK_CATEGORIES.items():
        scopes = meta.get("scope") or ()
        if scope and scope not in scopes:
            continue
        rows.append({"id": key, **meta})
    return rows

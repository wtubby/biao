"""暗标模式：读取开关、写作约束、违规检测与导出匿名化。"""

from __future__ import annotations

import re
from typing import Any

from db.models import Project
from services.tender_detail_service import get_tender_detail

# 招标文件中常见的暗标表述（关键词命中即高置信度预勾选）
_BLIND_BID_MARKERS = (
    "暗标",
    "匿名评审",
    "盲评",
    "不得出现投标人名称",
    "隐去投标人信息",
)

# 常见投标人/公司标识（暗标正文禁止出现）
_COMPANY_MARKERS = (
    "有限公司",
    "股份有限公司",
    "集团有限公司",
    "工程公司",
    "建设公司",
    "电力公司",
    "本公司",
    "我公司",
    "我方公司",
    "投标人名称",
    "投标单位",
)

_IDENTITY_PATTERNS = (
    re.compile(r"[\u4e00-\u9fff]{2,20}(?:有限公司|股份有限公司|集团)"),
    re.compile(r"(?:统一社会信用代码|组织机构代码)\s*[:：]?\s*[A-Z0-9]{10,}"),
    re.compile(r"(?:联系人|项目经理)\s*[:：]\s*[\u4e00-\u9fff]{2,4}(?![员工])"),
)


def detect_blind_bid(full_text: str) -> bool | None:
    """从招标文件原文轻量识别暗标。

    命中返回 True；未命中返回 None（不代表一定不是暗标，留给用户确认，不直接判 False）。
    """
    text = full_text or ""
    if not text.strip():
        return None
    for marker in _BLIND_BID_MARKERS:
        if marker in text:
            return True
    return None


def is_blind_bid(project: Project) -> bool:
    try:
        detail = get_tender_detail(project)
    except Exception:
        return False
    return detail.get("notice", {}).get("blind_bid") is True


def blind_bid_writer_constraints() -> str:
    return (
        "## 暗标约束（必须严格遵守）\n"
        "- 全文不得出现投标人/公司全称、简称、品牌口号、统一社会信用代码\n"
        "- 不得出现「本公司」「我公司」「我方公司」等可识别表述，改用「投标人」或直接写措施\n"
        "- 不得出现具体联系人姓名、电话、地址、公章描述\n"
        "- 封面与正文保持匿名；人员配置用岗位职责描述，不写真实姓名\n"
        "- 引用业绩时用「同类工程」「类似电压等级工程」概括，不写可追溯的业主全称与合同编号"
    )


def check_blind_bid_violations(content: str, project: Project | None = None) -> list[str]:
    """检测暗标违规；非暗标项目返回空列表。"""
    if project is not None and not is_blind_bid(project):
        return []
    text = content or ""
    if not text.strip():
        return []

    errors: list[str] = []
    for marker in _COMPANY_MARKERS:
        if marker in text:
            errors.append(f"暗标违规：出现「{marker}」")

    for pattern in _IDENTITY_PATTERNS:
        m = pattern.search(text)
        if m:
            snippet = m.group(0)[:40]
            errors.append(f"暗标违规：疑似身份信息「{snippet}」")

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            unique.append(err)
    return unique[:8]


def anonymize_cover_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """暗标封面：保留工程技术参数，去掉可识别编制单位信息。"""
    cleaned = dict(meta or {})
    cleaned.pop("bidder_name", None)
    cleaned.pop("company_name", None)
    cleaned["blind_bid"] = True
    return cleaned


def blind_header_text() -> str:
    return "技术方案（暗标）"

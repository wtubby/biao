"""从招标文件原文启发式摘录「投标文件参考格式」目录。

用于 LLM 截断或漏抽时回填 tender_detail.bid_reference_catalog。
优先技术标相关：施工组织设计纲要 / 项目实施方案；否则回落投标文件组成总目录。
"""

from __future__ import annotations

import re
from typing import Iterable

from services.document_parser import ParsedItem

_CN_DIGITS = "〇一二三四五六七八九十"

_BID_TOC_ANCHORS = (
    "投标函",
    "授权委托书",
    "法定代表人",
    "投标保证金",
    "资格审查",
    "报价清单",
    "项目实施方案",
    "商务标",
    "技术标",
    "技术部分",
    "商务部分",
)

_TECH_SECTION_HINTS = (
    "项目实施方案",
    "技术标",
    "技术部分",
    "技术文件",
    "施工组织设计",
    "技术方案",
)

_TOC_LINE_RE = re.compile(
    r"^([一二三四五六七八九十百]+)[、．.]\s*(.+)$"
)
_PAREN_CN_RE = re.compile(
    r"^[（(]\s*([一二三四五六七八九十百]+|\d{1,2})\s*[）)]\s*(.+)$"
)
_NUM_TITLE_RE = re.compile(
    # 优先匹配 4.3标题 / 4.3 标题，避免把「4.3」拆成「4.」+「3…」
    r"^(\d{1,2}(?:\.\d+)+)\s*[．、.]?\s*(.+)$"
    r"|^(\d{1,2})(?:[\s、．]+|\.\s+)(.+)$"
)
_OUTLINE_START_RE = re.compile(
    r"施工组织设计(?:纲要|大纲)|技术标(?:文件)?(?:组成|格式|目录)|"
    r"技术部分(?:组成|格式|目录)|项目实施方案.{0,12}(?:应包含|包括|内容|组成|编写)"
)


def _cn_index(n: int) -> str:
    if n <= 0:
        return str(n)
    if n <= 10:
        return "十" if n == 10 else _CN_DIGITS[n]
    if n < 20:
        return f"十{_CN_DIGITS[n - 10]}"
    tens, ones = divmod(n, 10)
    tens_part = "" if tens == 1 else _CN_DIGITS[tens]
    ones_part = _CN_DIGITS[ones] if ones else ""
    return f"{tens_part}十{ones_part}"


def _clean_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"[…\.．]{2,}.*$", "", title)
    title = re.sub(r"[.…]+$", "", title)
    title = re.sub(r"[（(]\s*[）)]\s*$", "", title)
    title = title.strip(" ：:.-—_")
    # 括号内是列举说明时，只保留括号前标题
    for left in ("（", "("):
        if left in title:
            head = title.split(left, 1)[0].strip()
            if 2 <= len(head) <= 30:
                title = head
                break
    # 描述性长句：取首个分句作标题
    for sep in ("，", ",", "；", ";"):
        if sep in title and len(title) > 18:
            title = title.split(sep, 1)[0].strip()
            break
    if "、" in title and len(title) > 20 and "（" not in title and "(" not in title:
        title = title.split("、", 1)[0].strip()
    title = re.sub(
        r"(要求内容全面|拟采取的措施|潜在问题的分析|为控制成本.*|应明确.*|等)$",
        "",
        title,
    ).strip(" 。.；;")
    # 「分包工程管理质量管理」类粘连：保留到「管理」首次完整语义
    title = re.sub(r"(管理)质量管理.*$", r"\1", title)
    if len(title) > 40:
        title = title[:40].rstrip()
    return title


def _iter_texts(items: Iterable[ParsedItem]) -> list[str]:
    texts: list[str] = []
    for item in items:
        text = (item.text or "").strip()
        if not text:
            continue
        # 表格单元格可能用 tab/换行拼成多行目录
        for part in re.split(r"[\r\n]+", text):
            line = part.strip()
            if line:
                texts.append(line)
    return texts


def _extract_bid_composition_toc(lines: list[str]) -> list[str]:
    """摘录「一、投标函… / 六、项目实施方案…」一类投标文件组成目录。"""
    best: list[str] = []
    i = 0
    while i < len(lines):
        m = _TOC_LINE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        block: list[tuple[str, str]] = []
        j = i
        while j < len(lines):
            mj = _TOC_LINE_RE.match(lines[j])
            if not mj:
                break
            num, title = mj.group(1), _clean_title(mj.group(2))
            if not title or len(title) > 60:
                break
            block.append((num, title))
            j += 1
        titles = [t for _, t in block]
        anchor_hits = sum(1 for t in titles if any(a in t for a in _BID_TOC_ANCHORS))
        if len(block) >= 3 and anchor_hits >= 2 and len(block) > len(best):
            best = [f"{num}、{title}" for num, title in block]
        i = max(j, i + 1)
    return best


def _extract_tech_outline_titles(lines: list[str]) -> list[str]:
    """从施工组织设计纲要 / 技术部分要求中摘录可作目录的标题行。"""
    starts = [idx for idx, line in enumerate(lines) if _OUTLINE_START_RE.search(line)]
    if not starts:
        return []

    best: list[str] = []
    for start in starts:
        titles: list[str] = []
        seen: set[str] = set()
        end = min(len(lines), start + 80)
        for line in lines[start + 1 : end]:
            if _TOC_LINE_RE.match(line) and any(a in line for a in _BID_TOC_ANCHORS):
                break
            if line.startswith("注：") or line.startswith("说明："):
                continue
            if re.match(r"^第[一二三四五六七八九十\d]+章", line):
                break
            if line.startswith("1.承包人") or line.startswith("允许分包"):
                break

            title = None
            for pattern in (_PAREN_CN_RE, _NUM_TITLE_RE, _TOC_LINE_RE):
                m = pattern.match(line)
                if m:
                    # 多分支正则：取最后一个非空捕获组作为标题
                    groups = [g for g in m.groups() if g]
                    title = _clean_title(groups[-1]) if groups else None
                    break
            if title is None:
                stripped = re.sub(r"^(简要叙述|要求|包括|含)", "", line).strip()
                if any(
                    k in stripped
                    for k in (
                        "工程", "施工", "质量", "安全", "进度", "平面",
                        "组织", "环保", "文明", "资源", "工序", "设计特点",
                    )
                ):
                    # 纲要中常见「工程简述，…等。」内容要点
                    if "，" in stripped or "、" in stripped or "等" in stripped or len(stripped) <= 40:
                        title = _clean_title(stripped)

            if not title or len(title) < 2:
                continue
            if title in seen:
                continue
            if any(
                x in title
                for x in ("不得", "必须严格执行", "违约", "本合同", "招标人提供", "按国家")
            ):
                continue
            if title.startswith(("用", "简要", "分析因", "当承包人", "无论", "针对")):
                continue
            if "应明确" in title or "应附" in title:
                continue
            seen.add(title)
            titles.append(title)
            if len(titles) >= 20:
                break
        if len(titles) > len(best):
            best = titles
    return best


def _format_tech_catalog(parent: str | None, titles: list[str]) -> str:
    lines: list[str] = []
    if parent:
        lines.append(parent if re.match(r"^[一二三四五六七八九十]+、", parent) else f"（一）{parent}")
    for idx, title in enumerate(titles, start=1):
        prefix = "  " if parent else ""
        if parent:
            lines.append(f"{prefix}{idx}. {title}")
        else:
            lines.append(f"（{_cn_index(idx)}）{title}")
    return "\n".join(lines)


def extract_bid_reference_catalog_from_items(items: list[ParsedItem]) -> str:
    """从解析后的全文条目中启发式提取参考格式目录文本；无可靠结果则返回空串。"""
    lines = _iter_texts(items)
    if not lines:
        return ""

    toc = _extract_bid_composition_toc(lines)
    tech_titles = _extract_tech_outline_titles(lines)

    tech_parent = None
    for entry in toc:
        if any(h in entry for h in _TECH_SECTION_HINTS):
            tech_parent = entry
            break

    if tech_titles and len(tech_titles) >= 2:
        return _format_tech_catalog(tech_parent, tech_titles)

    if toc and len(toc) >= 3:
        # 无细目录时，至少保留投标文件组成（含技术相关条目）
        return "\n".join(toc)

    if tech_titles:
        return _format_tech_catalog(tech_parent, tech_titles)

    return ""

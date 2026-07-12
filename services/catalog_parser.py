"""将用户粘贴的目录文本解析为结构化章节列表。"""

import re

from services.project_meta import is_valid_outline_catalog

LEVEL1_CN_RE = re.compile(r"^[（(]\s*([一二三四五六七八九十百]+)\s*[）)]\s*(.+)$")
LEVEL1_CHAPTER_RE = re.compile(r"^第\s*([一二三四五六七八九十百\d]+)\s*[章节部分篇]\s*(.+)$")
LEVEL1_ENUM_RE = re.compile(r"^([一二三四五六七八九十]+)\s*[、．.]\s*(.+)$")
LEVEL2_NUM_RE = re.compile(r"^(\d{1,2}(?:\.\d+)*)[\s.．、]+(.+)$")


def _clean_title(title: str) -> str:
    return title.strip().rstrip("。.．;；")


def _detect_level(line: str, explicit_indent: int) -> tuple[int, str] | None:
    stripped = line.strip()
    if not stripped:
        return None

    for pattern in (LEVEL1_CN_RE, LEVEL1_CHAPTER_RE, LEVEL1_ENUM_RE):
        match = pattern.match(stripped)
        if match:
            return 1, _clean_title(match.group(2))

    match = LEVEL2_NUM_RE.match(stripped)
    if match:
        num = match.group(1)
        depth = num.count(".") + 1
        return min(depth + 1, 4), _clean_title(match.group(2))

    if explicit_indent >= 2:
        return 2, _clean_title(stripped)

    return None


def parse_catalog_text(text: str) -> list[dict]:
    items: list[dict] = []
    sort_order = 0

    for raw in text.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        parsed = _detect_level(raw, indent)
        if not parsed:
            continue
        level, title = parsed
        if not title:
            continue
        sort_order += 1
        items.append({"title": title, "level": level, "sort_order": sort_order})

    return items if is_valid_outline_catalog(items) else []

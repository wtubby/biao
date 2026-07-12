"""从工期文本解析日历天数。"""

from __future__ import annotations

import re

# 个日历日/个日历天 须排在短后缀（日/天）之前，避免截断匹配
DURATION_DAYS_RE = re.compile(r"(\d+)\s*(个日历日|(?:个)?日历天|日历日|天|日)")


def parse_duration_days_from_text(text: str) -> int | None:
    if not text:
        return None
    m = DURATION_DAYS_RE.search(str(text))
    if m:
        return int(m.group(1))
    return None

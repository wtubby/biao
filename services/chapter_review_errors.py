"""章节 review_errors 的统一解析 / 序列化。"""

from __future__ import annotations

import json


def parse_review_errors(raw: str | list | None) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
        return [str(data)]
    except (TypeError, json.JSONDecodeError):
        return [str(raw)]


def dump_review_errors(errors: list[str] | None) -> str | None:
    if not errors:
        return None
    return json.dumps([str(x) for x in errors], ensure_ascii=False)


def merge_review_errors(raw: str | list | None, extra: list[str]) -> str:
    existing = parse_review_errors(raw)
    merged = list(dict.fromkeys(existing + [str(x) for x in extra]))
    return json.dumps(merged, ensure_ascii=False)

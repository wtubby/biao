"""评分项序列化（outline / prompt_debug 共用）。"""

from __future__ import annotations

from db.models import TechRequirement


def requirement_dicts(requirements: list[TechRequirement]) -> list[dict]:
    return [
        {
            "id": r.id,
            "title": r.requirement_title,
            "score_value": r.score_value,
            "is_risk_item": r.is_risk_item,
            "score_category": r.score_category,
        }
        for r in requirements
    ]

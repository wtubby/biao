from services.generation_mode import (
    GENERATION_MODE_COMPACT,
    GENERATION_MODE_FULL,
    scale_target_words,
    set_generation_mode,
)
from services.outline_service import enrich_outline_nodes
from services.writing_guidance import parse_writing_guidance
from db.models import Project


def _leaf_target_words(node: dict) -> int:
    parsed = parse_writing_guidance(node.get("writing_guidance"))
    return parsed["target_words"] or 0


def test_scale_target_words_compact():
    assert scale_target_words(1000, GENERATION_MODE_FULL) == 1000
    assert scale_target_words(1000, GENERATION_MODE_COMPACT) == 600
    assert scale_target_words(200, GENERATION_MODE_COMPACT) == 200


def test_enrich_outline_nodes_respects_compact_mode():
    nodes = [{
        "id": "1",
        "title": "施工组织",
        "is_leaf": 1,
        "requirement_ids": ["r1"],
        "guidance_brief": "写组织",
        "content_boundary": "写施工组织要点",
    }]
    requirements = [{
        "id": "r1",
        "title": "施工组织",
        "score_value": 10,
        "is_risk_item": 0,
    }]
    full = enrich_outline_nodes(nodes, requirements, target_pages=40, generation_mode=GENERATION_MODE_FULL)
    compact = enrich_outline_nodes(nodes, requirements, target_pages=40, generation_mode=GENERATION_MODE_COMPACT)
    assert _leaf_target_words(compact[0]) < _leaf_target_words(full[0])


def test_set_generation_mode_on_project():
    project = Project(id="p1", extra_params="{}")
    set_generation_mode(project, GENERATION_MODE_COMPACT)
    import json
    meta = json.loads(project.extra_params)
    assert meta["generation_mode"] == GENERATION_MODE_COMPACT

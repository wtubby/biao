"""章节上下文 bundle 组装。"""

import json
import logging

from sqlalchemy.orm import Session

from config import (
    IMMEDIATE_PRIOR_SIBLING_MAX_CHARS,
    KEY_CHAPTER_MIN_SCORE,
    WRITER_GUIDE_USER_MAX_CHARS,
    WRITER_SYSTEM_COMPACT,
)
from db.models import GlobalFact, Project, TechOutline, TechRequirement
from domains.registry import DEFAULT_DOMAIN
from prompts.writer_prompt import (
    build_key_chapter_init_prompt,
    compact_writing_guide,
    get_writer_system_prompt,
)
from services.blind_bid_service import blind_bid_writer_constraints, is_blind_bid
from services.generation_config import (
    chart_density_hint,
    get_generation_config,
    standards_pack_hint,
)
from services.project_meta import get_meta
from services.prompt_project_info import build_prompt_global_params
from services.reference_bid_service import build_reference_query, select_reference_bid_snippets
from services.requirement_prompt import (
    build_chapter_evaluation_focus,
    format_requirements_text,
    maybe_refine_evaluation_focus,
    requirements_response_hint,
)
from services.response_matrix_service import format_chapter_matrix_context
from services.retrieval_service import RetrievalResult, build_retrieval_warning, retrieve_detailed
from services.writing_guidance import (
    default_content_boundary_for_title,
    parse_writing_guidance,
)

logger = logging.getLogger(__name__)

_KEY_CHAPTER_KEYWORDS = ("施工方案", "技术方案", "施工组织", "总体方案", "专项方案")


def _root_ancestor_id(node: TechOutline, node_map: dict[str, TechOutline]) -> str:
    current = node
    while current.parent_id and current.parent_id in node_map:
        current = node_map[current.parent_id]
    return current.id


def _collect_sibling_leaf_titles(chapter: TechOutline, all_nodes: list[TechOutline]) -> list[str]:
    return [
        n.title.strip()
        for n in all_nodes
        if n.is_leaf == 1 and n.parent_id == chapter.parent_id and n.id != chapter.id
    ]


def _ordered_sibling_leaves(chapter: TechOutline, all_nodes: list[TechOutline]) -> list[TechOutline]:
    if not chapter.parent_id:
        return []
    return sorted(
        [
            n for n in all_nodes
            if n.is_leaf == 1 and n.parent_id == chapter.parent_id
        ],
        key=lambda x: x.sort_order,
    )


def _get_immediate_prior_sibling(
    chapter: TechOutline, all_nodes: list[TechOutline]
) -> tuple[str | None, str | None]:
    """紧邻上一同级叶子（同 parent_id）的标题与正文，供连贯性接力。"""
    siblings = _ordered_sibling_leaves(chapter, all_nodes)
    for i, leaf in enumerate(siblings):
        if leaf.id != chapter.id:
            continue
        if i == 0:
            return None, None
        prev = siblings[i - 1]
        body = (prev.generated_content or "").strip()
        if not body:
            return prev.title.strip() or None, None
        if len(body) > IMMEDIATE_PRIOR_SIBLING_MAX_CHARS:
            body = f"（…前文省略…）\n{body[-IMMEDIATE_PRIOR_SIBLING_MAX_CHARS:]}"
        return prev.title.strip() or None, body
    return None, None


def _collect_other_leaf_titles(chapter: TechOutline, all_nodes: list[TechOutline]) -> list[str]:
    return [
        n.title.strip()
        for n in all_nodes
        if n.is_leaf == 1 and n.id != chapter.id
    ]


def _default_content_boundary(chapter: TechOutline, sibling_titles: list[str]) -> str:
    typed_boundary = default_content_boundary_for_title(chapter.title)
    if typed_boundary:
        return typed_boundary
    parts = [
        f"仅撰写「{chapter.title}」对应正文，不输出章节标题行，不重复上一章摘要。",
    ]
    if sibling_titles:
        parts.append(f"不得涉及兄弟章节：{'、'.join(sibling_titles)}。")
    return "".join(parts)


def group_leaves_by_section(leaves: list[TechOutline], all_nodes: list[TechOutline]) -> list[list[TechOutline]]:
    node_map = {n.id: n for n in all_nodes}
    groups: dict[str, list[TechOutline]] = {}
    for leaf in sorted(leaves, key=lambda x: x.sort_order):
        root_id = _root_ancestor_id(leaf, node_map)
        groups.setdefault(root_id, []).append(leaf)
    return list(groups.values())


def _is_key_chapter(chapter: TechOutline, requirements: list[TechRequirement]) -> bool:
    if any(kw in chapter.title for kw in _KEY_CHAPTER_KEYWORDS):
        return True
    score = sum(float(r.score_value or 0) for r in requirements)
    return score >= KEY_CHAPTER_MIN_SCORE


def build_context_bundle(
    db: Session,
    project: Project,
    chapter: TechOutline,
    section_leaves: list[TechOutline] | None = None,
    entry_summary: str | None = None,
    use_section_summary_pool: bool = False,
) -> dict:
    req_ids = json.loads(chapter.requirement_ids or "[]")
    requirements = (
        db.query(TechRequirement).filter(TechRequirement.id.in_(req_ids)).all()
        if req_ids
        else []
    )
    req_text = format_requirements_text(requirements)
    req_hint = requirements_response_hint(requirements)

    all_nodes = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project.id)
        .order_by(TechOutline.sort_order)
        .all()
    )
    path_parts = []
    current = chapter
    node_map = {n.id: n for n in all_nodes}
    while current:
        path_parts.insert(0, current.title)
        current = node_map.get(current.parent_id) if current.parent_id else None

    guidance_preview = parse_writing_guidance(chapter.writing_guidance)
    query_parts = [
        chapter.title,
        " ".join(r.requirement_title for r in requirements),
        guidance_preview.get("brief") or "",
        guidance_preview.get("content_boundary") or "",
    ]
    for r in requirements:
        if r.keyword:
            query_parts.append(r.keyword)
        if r.mandatory_elements:
            query_parts.append(r.mandatory_elements)
        if r.source_text:
            query_parts.append((r.source_text or "")[:400])
    query = " ".join(p for p in query_parts if p).strip()
    gen_config = get_generation_config(project)
    if gen_config.get("use_knowledge_library", True):
        retrieval = retrieve_detailed(query, chapter.bound_folder, project_id=project.id, db=db)
        chunks = retrieval.chunks
    else:
        retrieval = RetrievalResult(chunks=[], empty_reason="已关闭自有知识库")
        chunks = []

    facts = (
        db.query(GlobalFact)
        .filter(GlobalFact.project_id == project.id)
        .order_by(GlobalFact.sort_order)
        .all()
    )
    facts_text = "\n\n".join(
        f"【{f.title}】\n{f.content}" for f in facts if f.content.strip()
    )

    meta = get_meta(project)
    domain = meta.get("engineering_domain") or DEFAULT_DOMAIN
    contradictions = meta.get("contradictions") or []
    if not isinstance(contradictions, list):
        contradictions = []
    retrieval_warning = build_retrieval_warning(
        domain,
        chapter.bound_folder,
        retrieval.empty_reason,
        has_chunks=bool(chunks),
    )
    guidance = guidance_preview
    sibling_leaf_titles = _collect_sibling_leaf_titles(chapter, all_nodes)
    other_leaf_titles = _collect_other_leaf_titles(chapter, all_nodes)
    if not guidance.get("content_boundary"):
        guidance["content_boundary"] = _default_content_boundary(chapter, sibling_leaf_titles)
    all_leaf_nodes = [n for n in all_nodes if n.is_leaf == 1]
    if use_section_summary_pool and section_leaves:
        summary_pool = section_leaves
    else:
        summary_pool = all_leaf_nodes
    last_summary = _get_prev_summary(summary_pool, chapter)
    if not last_summary and entry_summary and section_leaves and chapter.id == section_leaves[0].id:
        last_summary = entry_summary
    prior_summaries = _collect_prior_summaries(summary_pool, chapter, limit=5)
    prior_contents = _collect_prior_contents(summary_pool, chapter, limit=3)
    immediate_prior_title, immediate_prior_body = _get_immediate_prior_sibling(chapter, all_nodes)
    overview = (meta.get("extra_notes") or "").strip() or None
    global_params = build_prompt_global_params(project)
    empty_retrieval_hint = None
    if not chunks:
        if not gen_config.get("use_knowledge_library", True):
            empty_retrieval_hint = (
                "已关闭自有知识库：请基于评分项、工程参数与项目概况撰写；"
                "禁止编造规范标准号与未提供的品牌型号。"
            )
        elif retrieval.empty_reason:
            empty_retrieval_hint = (
                "本节无可用检索素材：请基于评分项、工程参数与项目概况撰写；"
                "禁止编造规范标准号与未提供的品牌型号；缺数据处用 **[参数] 待核实** 标注。"
            )

    ref_raw = ""
    if gen_config.get("reference_bid_enabled"):
        ref_raw = (gen_config.get("reference_bid_text") or "").strip()
    ref_query = build_reference_query(
        chapter.title,
        guidance,
        [r.requirement_title for r in requirements],
    )
    reference_bid_text = select_reference_bid_snippets(ref_raw, ref_query) if ref_raw else ""
    reference_bid_miss = bool(ref_raw) and not bool(reference_bid_text)

    standards_hint = standards_pack_hint(
        gen_config.get("standards_pack") or "epc_guide",
        chapter_title=chapter.title,
        brief=guidance.get("brief") or "",
        boundary=guidance.get("content_boundary") or "",
    )

    blind = is_blind_bid(project)
    matrix_context = format_chapter_matrix_context(chapter, requirements, all_nodes)
    evaluation_focus = build_chapter_evaluation_focus(
        chapter.title, requirements, global_params,
    )
    writing_guide_excerpt = (
        compact_writing_guide(domain, WRITER_GUIDE_USER_MAX_CHARS)
        if WRITER_SYSTEM_COMPACT
        else ""
    )

    bundle = {
        "global_params": global_params,
        "project_overview": overview,
        "engineering_domain": domain,
        "requirements_text": req_text,
        "requirements_hint": req_hint,
        "matrix_context": matrix_context,
        "evaluation_focus": evaluation_focus,
        "writing_guide_excerpt": writing_guide_excerpt,
        "retrieval_text": "\n\n---\n\n".join(chunks),
        "retrieval_warning": retrieval_warning,
        "empty_retrieval_hint": empty_retrieval_hint,
        "last_summary": last_summary,
        "chapter_id": chapter.id,
        "chapter_parent_id": chapter.parent_id,
        "chapter_title": chapter.title,
        "chapter_level": chapter.level,
        "chapter_path": " > ".join(path_parts),
        "immediate_prior_sibling_title": immediate_prior_title,
        "immediate_prior_sibling_body": immediate_prior_body,
        "guidance": guidance,
        "requirements": requirements,
        "all_nodes": all_nodes,
        "global_facts_text": facts_text,
        "sibling_leaf_titles": sibling_leaf_titles,
        "other_leaf_titles": other_leaf_titles,
        "chart_density_hint": chart_density_hint(gen_config.get("chart_density") or "normal"),
        "standards_hint": standards_hint,
        "reference_bid_text": reference_bid_text,
        "reference_bid_miss": reference_bid_miss,
        "blind_bid": blind,
        "blind_bid_constraints": blind_bid_writer_constraints() if blind else "",
        "prior_summaries": prior_summaries,
        "prior_contents": prior_contents,
        "contradictions": contradictions,
    }
    bundle["evaluation_focus"] = maybe_refine_evaluation_focus(
        bundle["evaluation_focus"], bundle,
    )
    return bundle


def _get_prev_summary(leaves: list[TechOutline], current: TechOutline) -> str | None:
    ordered = sorted(leaves, key=lambda x: x.sort_order)
    for i, leaf in enumerate(ordered):
        if leaf.id == current.id and i > 0:
            return ordered[i - 1].last_summary
    return None


def _collect_prior_summaries(
    leaves: list[TechOutline], current: TechOutline, *, limit: int = 5
) -> list[str]:
    ordered = sorted(leaves, key=lambda x: x.sort_order)
    collected: list[str] = []
    for leaf in ordered:
        if leaf.id == current.id:
            break
        summary = (leaf.last_summary or "").strip()
        if summary:
            collected.append(f"「{leaf.title}」{summary}")
    return collected[-limit:]


def _collect_prior_contents(
    leaves: list[TechOutline], current: TechOutline, *, limit: int = 3
) -> list[str]:
    ordered = sorted(leaves, key=lambda x: x.sort_order)
    collected: list[str] = []
    for leaf in ordered:
        if leaf.id == current.id:
            break
        body = (leaf.generated_content or "").strip()
        if len(body) >= 120:
            collected.append(body[:2500])
    return collected[-limit:]


def _enrich_retrieval_with_plan(
    bundle: dict,
    project: Project,
    chapter: TechOutline,
    db: Session,
) -> None:
    """规划产出 retrieval_focus 后二次检索，合并素材。"""
    plan = bundle.get("content_plan") or {}
    focus = [str(x).strip() for x in (plan.get("retrieval_focus") or []) if str(x).strip()]
    if not focus:
        focus = [str(x).strip() for x in (plan.get("key_points") or [])[:3] if str(x).strip()]
    if not focus:
        return
    gen_config = get_generation_config(project)
    if not gen_config.get("use_knowledge_library", True):
        return
    query = " ".join([chapter.title or "", *focus])
    try:
        extra = retrieve_detailed(query, chapter.bound_folder, project_id=project.id, db=db)
    except Exception as exc:
        logger.warning("规划二次检索失败: %s", exc)
        return
    if not extra.chunks:
        return
    existing = (bundle.get("retrieval_text") or "").strip()
    merged = existing.split("\n\n---\n\n") if existing and existing != "（无检索素材）" else []
    for chunk in extra.chunks:
        if chunk and chunk not in merged:
            merged.append(chunk)
    bundle["retrieval_text"] = "\n\n---\n\n".join(merged[:8])
    if merged:
        bundle["empty_retrieval_hint"] = None
        bundle["retrieval_warning"] = None


def _init_key_chapter_messages(
    db: Session,
    project: Project,
    requirements: list[TechRequirement],
    all_nodes: list[TechOutline],
) -> list[dict]:
    meta = get_meta(project)
    domain = meta.get("engineering_domain") or DEFAULT_DOMAIN
    overview = (meta.get("extra_notes") or "").strip() or None
    all_reqs = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id, TechRequirement.status == "confirmed")
        .all()
    )
    outline_titles = [n.title for n in sorted(all_nodes, key=lambda x: x.sort_order)]
    init_prompt = build_key_chapter_init_prompt(
        project, all_reqs or requirements, outline_titles, domain, overview=overview,
    )
    return [
        {"role": "system", "content": get_writer_system_prompt(domain)},
        {"role": "user", "content": init_prompt},
        {
            "role": "assistant",
            "content": f"已理解项目背景、评分项与大纲结构，将按{domain}技术标规范逐章撰写。",
        },
    ]



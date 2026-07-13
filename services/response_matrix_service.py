"""评分项响应矩阵：把评分项、大纲绑定与生成正文覆盖串起来。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from db.models import Project, TechOutline, TechRequirement
from services.outline_order import sort_outline_tree_dfs
from services.chapter_review_errors import merge_review_errors
from services.project_meta import get_meta
from services.qa_rules import (
    extract_coverage_candidates,
    mandatory_element_covered,
    match_coverage_candidates,
    split_mandatory_elements,
)


def _load_requirement_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def _evidence_snippet(text: str, candidates: list[str], window: int = 60) -> str:
    if not text:
        return ""
    for candidate in candidates:
        if not candidate:
            continue
        pos = text.find(candidate)
        if pos >= 0:
            start = max(0, pos - window)
            end = min(len(text), pos + len(candidate) + window)
            return text[start:end].strip()
    return ""


def _status_for_row(bound_chapters: list[dict[str, Any]], missing_elements: list[str], ignored: bool) -> str:
    if ignored:
        return "ignored"
    if not bound_chapters:
        return "unbound"
    if any(ch["has_content"] and ch["matched_keywords"] for ch in bound_chapters) and not missing_elements:
        return "covered"
    if any(ch["has_content"] for ch in bound_chapters):
        return "partial"
    return "bound_pending"


def _chapter_coverage_for_requirement(
    chapter: TechOutline,
    req: TechRequirement,
    *,
    content: str | None = None,
) -> dict[str, Any]:
    text = content if content is not None else (chapter.generated_content or "")
    candidates = extract_coverage_candidates(req.requirement_title, req.keyword)
    matched = match_coverage_candidates(text, candidates)
    missing_elements = [
        element
        for element in split_mandatory_elements(req.mandatory_elements)
        if not mandatory_element_covered(text, element)
    ]
    return {
        "requirement_id": req.id,
        "title": req.requirement_title,
        "is_risk_item": req.is_risk_item,
        "matched_keywords": matched,
        "missing_elements": missing_elements,
        "has_content": bool(text.strip()),
        "candidates": candidates,
    }


def format_chapter_matrix_context(
    chapter: TechOutline,
    requirements: list[TechRequirement],
    all_nodes: list[TechOutline],
) -> str:
    """生成前注入：本章评分项分工与兄弟章已写摘要，防重复与漏项。"""
    if not requirements:
        return ""

    req_ids = {r.id for r in requirements}
    peers_by_req: dict[str, list[TechOutline]] = {}
    for node in all_nodes:
        if not node.is_leaf:
            continue
        for req_id in _load_requirement_ids(node.requirement_ids):
            if req_id in req_ids:
                peers_by_req.setdefault(req_id, []).append(node)

    lines = ["【本章评分响应矩阵】"]
    for req in requirements:
        score = float(req.score_value or 0)
        score_part = f"（{score:g}分）" if score > 0 else ""
        risk_part = " [刚性]" if int(req.is_risk_item or 0) == 1 else ""
        mandatory = (req.mandatory_elements or "").strip()
        mandatory_part = f"；必备要素：{mandatory}" if mandatory else ""

        peers = [ch for ch in peers_by_req.get(req.id, []) if ch.id != chapter.id]
        peer_titles = [ch.title for ch in peers if ch.title]
        if peer_titles:
            peer_part = f"；同项还绑定：{'、'.join(peer_titles[:6])}"
            if len(peer_titles) > 6:
                peer_part += f" 等共 {len(peer_titles)} 章"
        else:
            peer_part = "；同项仅绑定本章"

        title = req.requirement_title or req.id
        lines.append(f"- 「{title}」{score_part}{risk_part}{mandatory_part}{peer_part}")

        peer_notes: list[str] = []
        for ch in peers:
            summary = (ch.last_summary or "").strip()
            if summary:
                peer_notes.append(f"「{ch.title}」已写摘要：{summary[:100]}")
                continue
            body = (ch.generated_content or "").strip()
            if len(body) >= 80:
                peer_notes.append(f"「{ch.title}」已有正文（勿重复展开同类措施）")
        for note in peer_notes[:3]:
            lines.append(f"  · {note}")

    return "\n".join(lines)


def matrix_issues_for_chapter(
    db: Session,
    project: Project,
    chapter: TechOutline,
) -> list[str]:
    """单章绑定评分项的覆盖缺口，供生成后回写 review_errors。

    同一评分项绑定多章时，与响应矩阵汇总一致：合并全部绑定叶子正文后再判覆盖，
    避免分工写作被单章误判为刚性缺口。
    """
    req_ids = _load_requirement_ids(chapter.requirement_ids)
    if not req_ids:
        return []
    requirements = (
        db.query(TechRequirement)
        .filter(
            TechRequirement.project_id == project.id,
            TechRequirement.id.in_(req_ids),
            TechRequirement.status != "ignored",
        )
        .all()
    )
    if not requirements:
        return []

    content = (chapter.generated_content or "").strip()
    if not content:
        return [f"评分覆盖：章节「{chapter.title}」正文为空，无法覆盖已绑定评分项"]

    leaves = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project.id, TechOutline.is_leaf == 1)
        .all()
    )
    chapters_by_req: dict[str, list[TechOutline]] = {}
    for node in leaves:
        for rid in _load_requirement_ids(node.requirement_ids):
            if rid in req_ids:
                chapters_by_req.setdefault(rid, []).append(node)

    issues: list[str] = []
    for req in requirements:
        bound = chapters_by_req.get(req.id) or [chapter]
        combined = "\n".join((ch.generated_content or "") for ch in bound)
        cov = _chapter_coverage_for_requirement(chapter, req, content=combined)
        title = req.requirement_title or req.id
        is_risk = int(req.is_risk_item or 0) == 1
        prefix = "刚性风险项" if is_risk else "评分项"
        if cov["missing_elements"]:
            issues.append(
                f"{prefix}「{title}」评分覆盖不足：缺少必备要素 "
                f"{', '.join(cov['missing_elements'])}"
            )
        elif cov["candidates"] and not cov["matched_keywords"]:
            issues.append(
                f"{prefix}「{title}」关键词未在正文中体现"
                f"（期望：{', '.join(cov['candidates'][:5])}）"
            )
    return issues


def apply_matrix_coverage_to_leaves(
    db: Session,
    project: Project,
    leaves: list[TechOutline] | None = None,
) -> int:
    """批量收尾：对有正文的叶子补写评分覆盖缺口。

    普通评分项缺口：green → yellow；
    刚性风险项缺口：直接打 red，以便导出拦截自动生效。
    """
    if leaves is None:
        leaves = (
            db.query(TechOutline)
            .filter(TechOutline.project_id == project.id, TechOutline.is_leaf == 1)
            .all()
        )
    changed = 0
    for chapter in leaves:
        if not (chapter.generated_content or "").strip():
            continue
        if chapter.review_status not in ("green", "yellow"):
            continue
        issues = matrix_issues_for_chapter(db, project, chapter)
        if not issues:
            continue
        chapter.review_errors = merge_review_errors(chapter.review_errors, issues)
        risk_issues = [i for i in issues if i.startswith("刚性风险项")]
        if risk_issues:
            # 刚性/否决项未覆盖：与生成失败同级，必须修复后才能导出
            chapter.review_status = "red"
        elif chapter.review_status == "green":
            chapter.review_status = "yellow"
        changed += 1
    return changed


def build_response_matrix(db: Session, project: Project) -> dict[str, Any]:
    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id)
        .order_by(TechRequirement.is_risk_item.desc(), TechRequirement.score_value.desc())
        .all()
    )
    chapters = sort_outline_tree_dfs(
        db.query(TechOutline).filter(TechOutline.project_id == project.id).all()
    )
    leaf_chapters = [ch for ch in chapters if ch.is_leaf == 1]
    chapters_by_req: dict[str, list[TechOutline]] = {}
    for chapter in leaf_chapters:
        for req_id in _load_requirement_ids(chapter.requirement_ids):
            chapters_by_req.setdefault(req_id, []).append(chapter)

    rows: list[dict[str, Any]] = []
    summary = {
        "total": len(requirements),
        "covered": 0,
        "partial": 0,
        "bound_pending": 0,
        "unbound": 0,
        "ignored": 0,
        "risk_total": sum(1 for req in requirements if req.is_risk_item == 1),
        "risk_uncovered": 0,
    }

    for req in requirements:
        candidates = extract_coverage_candidates(req.requirement_title, req.keyword)
        bound_chapters: list[dict[str, Any]] = []
        combined_text = ""
        for chapter in chapters_by_req.get(req.id, []):
            content = chapter.generated_content or ""
            combined_text += "\n" + content
            matched = match_coverage_candidates(content, candidates)
            bound_chapters.append({
                "id": chapter.id,
                "title": chapter.title,
                "review_status": chapter.review_status,
                "has_content": bool(content.strip()),
                "matched_keywords": matched,
                "evidence": _evidence_snippet(content, matched),
            })

        missing_elements = [
            element
            for element in split_mandatory_elements(req.mandatory_elements)
            if not mandatory_element_covered(combined_text, element)
        ]
        status = _status_for_row(bound_chapters, missing_elements, req.status == "ignored")
        summary[status] = summary.get(status, 0) + 1
        if req.is_risk_item == 1 and status not in ("covered", "ignored"):
            summary["risk_uncovered"] += 1

        rows.append({
            "requirement_id": req.id,
            "title": req.requirement_title,
            "score_value": req.score_value,
            "score_category": req.score_category,
            "source_page": req.source_page,
            "is_risk_item": req.is_risk_item,
            "keyword": req.keyword,
            "mandatory_elements": req.mandatory_elements,
            "status": status,
            "missing_elements": missing_elements,
            "bound_chapters": bound_chapters,
        })

    meta = get_meta(project)
    contradictions = meta.get("contradictions")
    return {
        "project_id": project.id,
        "summary": summary,
        "rows": rows,
        "contradictions": contradictions if isinstance(contradictions, list) else [],
    }

"""评分项响应矩阵：把评分项、大纲绑定与生成正文覆盖串起来。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from db.models import Project, TechOutline, TechRequirement
from services.outline_order import sort_outline_tree_dfs
from services.chapter_review_errors import dump_review_errors, parse_review_errors
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
    """生成前注入：仅输出「同项还绑定」增量（完整评分项见 requirements_text）。"""
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

    lines: list[str] = []
    for req in requirements:
        peers = [ch for ch in peers_by_req.get(req.id, []) if ch.id != chapter.id]
        peer_titles = [ch.title for ch in peers if ch.title]
        if not peer_titles:
            continue

        title = req.requirement_title or req.id
        peer_part = f"同项还绑定：{'、'.join(peer_titles[:6])}"
        if len(peer_titles) > 6:
            peer_part += f" 等共 {len(peer_titles)} 章"
        lines.append(f"- 「{title}」{peer_part}")

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

    if not lines:
        return ""
    return "【评分项分工提醒】\n" + "\n".join(lines)


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


def _is_matrix_coverage_issue(msg: str) -> bool:
    """识别 matrix_issues_for_chapter 写出的条目（与硬质检措辞刻意区分）。"""
    if not msg:
        return False
    if msg.startswith("评分覆盖："):
        return True
    if msg.startswith(("评分项", "刚性风险项")) and (
        "评分覆盖不足：缺少必备要素" in msg
        or "关键词未在正文中体现（期望：" in msg
    ):
        return True
    return False


def apply_matrix_coverage_to_leaves(
    db: Session,
    project: Project,
    leaves: list[TechOutline] | None = None,
) -> int:
    """批量收尾：清空旧矩阵缺口后按合并正文重判。

    普通评分项缺口：green → yellow；
    刚性风险项缺口：直接打 red，以便导出拦截自动生效。
    覆盖已齐全时会清掉过期的矩阵告警，并在无其它问题时回退 green。
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
        if chapter.review_status == "generating":
            continue

        existing = parse_review_errors(chapter.review_errors)
        non_matrix = [e for e in existing if not _is_matrix_coverage_issue(e)]
        had_matrix = len(non_matrix) < len(existing)
        had_matrix_risk = any(
            _is_matrix_coverage_issue(e) and e.startswith("刚性风险项") for e in existing
        )

        try:
            issues = matrix_issues_for_chapter(db, project, chapter)
        except Exception:
            continue

        prev_status = chapter.review_status
        prev_errors = chapter.review_errors

        if issues:
            chapter.review_errors = dump_review_errors(
                list(dict.fromkeys(non_matrix + issues))
            )
            if any(i.startswith("刚性风险项") for i in issues):
                chapter.review_status = "red"
            elif chapter.review_status == "green":
                chapter.review_status = "yellow"
            elif (
                chapter.review_status == "red"
                and had_matrix_risk
                and not non_matrix
                and not any(i.startswith("刚性风险项") for i in issues)
            ):
                # 旧刚性误判已解除，仅剩普通评分缺口 → yellow
                chapter.review_status = "yellow"
        else:
            chapter.review_errors = dump_review_errors(non_matrix)
            if had_matrix_risk and chapter.review_status == "red":
                chapter.review_status = "yellow" if non_matrix else "green"
            elif chapter.review_status == "yellow" and not non_matrix and had_matrix:
                chapter.review_status = "green"

        if (
            chapter.review_status != prev_status
            or chapter.review_errors != prev_errors
        ):
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

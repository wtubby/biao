"""规划期长叶子章节结构化拆分（Phase 2）。"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from config import (
    LONG_LEAF_MAX_LEVEL,
    LONG_LEAF_SPLIT_MAX_CHILDREN,
    LONG_LEAF_SPLIT_MIN_CHILDREN,
    LONG_LEAF_SPLIT_TARGET_PER_CHILD,
    LONG_LEAF_SPLIT_THRESHOLD,
    TARGET_PAGES_DEFAULT,
)
from db.models import Project, TechOutline, TechRequirement
from llm.llm_client import call_llm_json
from prompts.outline_split_prompt import build_split_user_prompt, get_split_system_prompt
from services.generation_mode import get_generation_mode
from services.outline_boundary_rules import sanitize_leaf_content_boundaries
from services.outline_service import (
    _global_engineering_info,
    _outline_rows_to_enrich_nodes,
    _req_dicts,
    enrich_outline_nodes,
    get_outline_tree,
    save_outline_tree,
)
from services.project_meta import get_meta, set_meta
from services.writing_guidance import (
    default_content_boundary_for_title,
    is_descriptive_chapter,
    parse_writing_guidance,
    serialize_writing_guidance,
)

logger = logging.getLogger(__name__)


def leaf_target_words(node: dict) -> int:
    tw = node.get("target_words")
    if tw is not None and int(tw or 0) > 0:
        return int(tw)
    parsed = parse_writing_guidance(node.get("writing_guidance"))
    return int(parsed.get("target_words") or 0)


def is_splittable_leaf(node: dict, *, threshold: int | None = None) -> tuple[bool, str]:
    threshold = threshold if threshold is not None else LONG_LEAF_SPLIT_THRESHOLD
    if int(node.get("is_leaf") or 0) != 1:
        return False, "非叶子节点"
    level = int(node.get("level") or 1)
    if level >= LONG_LEAF_MAX_LEVEL:
        return False, f"已达最大层级 {LONG_LEAF_MAX_LEVEL}，无法再拆"
    words = leaf_target_words(node)
    if words < threshold:
        return False, f"目标字数 {words} 低于阈值 {threshold}"
    if is_descriptive_chapter(node.get("title")):
        return False, "概况/目标类章节不参与结构拆分"
    return True, ""


def find_long_leaves(nodes: list[dict], *, threshold: int | None = None) -> list[dict]:
    return [n for n in nodes if is_splittable_leaf(n, threshold=threshold)[0]]


def _sibling_leaf_titles(leaf: dict, nodes: list[dict]) -> list[str]:
    pid = leaf.get("parent_id")
    return [
        str(n.get("title") or "").strip()
        for n in nodes
        if int(n.get("is_leaf") or 0) == 1
        and n.get("parent_id") == pid
        and n.get("id") != leaf.get("id")
    ]


def _chapter_path(leaf: dict, node_map: dict[str, dict]) -> str:
    parts: list[str] = []
    current: dict | None = leaf
    while current:
        parts.insert(0, str(current.get("title") or ""))
        pid = current.get("parent_id")
        current = node_map.get(pid) if pid else None
    return " > ".join(parts)


def validate_split_nodes(
    raw_nodes: list[Any],
    *,
    min_children: int = LONG_LEAF_SPLIT_MIN_CHILDREN,
    max_children: int = LONG_LEAF_SPLIT_MAX_CHILDREN,
    allowed_req_ids: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    issues: list[str] = []
    if not raw_nodes:
        return [], ["LLM 未返回子节点"]
    if len(raw_nodes) < min_children:
        issues.append(f"子节点数量 {len(raw_nodes)} 少于 {min_children}")
    if len(raw_nodes) > max_children:
        issues.append(f"子节点数量 {len(raw_nodes)} 超过 {max_children}")
    cleaned: list[dict] = []
    allowed = {str(x) for x in allowed_req_ids} if allowed_req_ids is not None else None
    for i, item in enumerate(raw_nodes):
        if not isinstance(item, dict):
            issues.append(f"第 {i + 1} 个子节点格式无效")
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            issues.append(f"第 {i + 1} 个子节点缺少标题")
            continue
        brief = str(item.get("guidance_brief") or item.get("writing_guidance") or "").strip()
        boundary = str(item.get("content_boundary") or "").strip()
        if not brief:
            issues.append(f"子节点「{title}」缺少写作要点")
            continue
        if not boundary:
            boundary = default_content_boundary_for_title(title) or (
                f"仅撰写「{title}」对应正文；不输出章节标题行；与前后子节点主题不重叠。"
            )
        req_ids = _normalize_req_ids(item.get("requirement_ids"), allowed=allowed)
        cleaned.append({
            # 不信任 LLM 的 id_suffix（可能重复）；按有效子节点顺序重编号
            "id_suffix": str(len(cleaned) + 1),
            "title": title,
            "guidance_brief": brief,
            "content_boundary": boundary,
            "requirement_ids": req_ids,
        })
    if len(cleaned) < min_children:
        issues.append("有效子节点不足")
    for i, item in enumerate(cleaned, start=1):
        item["id_suffix"] = str(i)
    return cleaned, issues


def _normalize_req_ids(raw: Any, *, allowed: set[str] | None) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        rid = str(item or "").strip()
        if not rid or rid in seen:
            continue
        if allowed is not None and rid not in allowed:
            continue
        seen.add(rid)
        out.append(rid)
    return out


def _match_tokens(text: str) -> set[str]:
    return set(re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z0-9]{2,}", text or ""))


def _assign_requirement_ids(
    child_specs: list[dict],
    parent_req_ids: list[str],
    requirements: list[dict] | None = None,
) -> list[dict]:
    """以 LLM 分配为主；未覆盖的父评分项兜底挂到最相关（或第一个）子节点。"""
    allowed = [str(x) for x in parent_req_ids if str(x).strip()]
    allowed_set = set(allowed)
    req_map = {
        str(r.get("id")): r
        for r in (requirements or [])
        if str(r.get("id") or "") in allowed_set
    }

    assigned: list[dict] = []
    claimed: set[str] = set()
    for spec in child_specs:
        ids = _normalize_req_ids(spec.get("requirement_ids"), allowed=allowed_set)
        claimed.update(ids)
        assigned.append({**spec, "requirement_ids": ids})

    if not assigned:
        return assigned

    uncovered = [rid for rid in allowed if rid not in claimed]
    for rid in uncovered:
        req = req_map.get(rid) or {}
        req_text = " ".join(
            str(req.get(k) or "")
            for k in ("title", "keyword", "mandatory_elements")
        )
        req_tokens = _match_tokens(req_text)
        best_idx = 0
        best_score = -1
        for i, spec in enumerate(assigned):
            child_text = " ".join(
                str(spec.get(k) or "")
                for k in ("title", "guidance_brief", "content_boundary")
            )
            score = len(req_tokens & _match_tokens(child_text)) if req_tokens else 0
            if score > best_score:
                best_score = score
                best_idx = i
        # best_score == 0 时保持第一个子节点（best_idx 初值为 0）
        cur = list(assigned[best_idx]["requirement_ids"])
        if rid not in cur:
            cur.append(rid)
        assigned[best_idx] = {**assigned[best_idx], "requirement_ids": cur}
    return assigned


def _split_requirement_dicts(requirements: list[TechRequirement]) -> list[dict]:
    """拆分专用：含 keyword / mandatory_elements，便于归属判断。"""
    return [
        {
            "id": r.id,
            "title": r.requirement_title,
            "score_value": r.score_value,
            "keyword": r.keyword or "",
            "mandatory_elements": r.mandatory_elements or "",
        }
        for r in requirements
    ]


def call_structured_split(
    leaf: dict,
    nodes: list[dict],
    global_info: dict,
    requirements: list[dict],
) -> tuple[list[dict], list[str]]:
    target_words = leaf_target_words(leaf)
    per_child = max(
        400,
        target_words // LONG_LEAF_SPLIT_MIN_CHILDREN if target_words else LONG_LEAF_SPLIT_TARGET_PER_CHILD,
    )
    node_map = {n["id"]: n for n in nodes}
    domain = global_info.get("工程领域")
    parent_req_ids = [str(x) for x in (leaf.get("requirement_ids") or [])]
    allowed = set(parent_req_ids)
    bound_reqs = [r for r in requirements if str(r.get("id")) in allowed]
    messages = [
        {"role": "system", "content": get_split_system_prompt(domain)},
        {
            "role": "user",
            "content": build_split_user_prompt(
                global_info=global_info,
                leaf=leaf,
                parent_path=_chapter_path(leaf, node_map),
                sibling_titles=_sibling_leaf_titles(leaf, nodes),
                requirements=bound_reqs,
                target_words=target_words,
                per_child_words=per_child,
            ),
        },
    ]
    try:
        result = call_llm_json(
            messages,
            max_tokens=2500,
            timeout=90.0,
            max_retries=2,
            truncation_hint="上次 JSON 被截断，请减少 content_boundary 字数并输出完整 3~4 个子节点。",
        )
    except Exception as exc:
        logger.warning("结构拆分 LLM 失败 leaf=%s: %s", leaf.get("id"), exc)
        return [], [f"AI 拆分失败：{exc}"]

    raw = result.get("nodes") if isinstance(result, dict) else []
    if not isinstance(raw, list):
        return [], ["LLM 返回格式无效"]
    return validate_split_nodes(raw, allowed_req_ids=allowed)


def _reorder_outline_nodes(nodes: list[dict]) -> list[dict]:
    id_map = {str(n["id"]): dict(n) for n in nodes}
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        children.setdefault(pid, []).append(str(n["id"]))
    for ids in children.values():
        ids.sort(key=lambda i: (id_map[i].get("sort_order") or 0, i))

    ordered: list[dict] = []

    def visit(parent_id: str | None, level: int) -> None:
        for nid in children.get(parent_id, []):
            node = id_map[nid]
            node["level"] = level
            ordered.append(node)
            if not node.get("is_leaf"):
                visit(nid, level + 1)

    visit(None, 1)
    for i, node in enumerate(ordered, start=1):
        node["sort_order"] = i
    return ordered


def apply_leaf_split(
    nodes: list[dict],
    leaf_id: str,
    child_specs: list[dict],
    requirements: list[dict] | None = None,
) -> list[dict]:
    node_map = {str(n["id"]): dict(n) for n in nodes}
    leaf = node_map.get(leaf_id)
    if not leaf:
        raise ValueError("章节不存在")
    if int(leaf.get("is_leaf") or 0) != 1:
        raise ValueError("仅支持拆分叶子章节")

    parent_words = leaf_target_words(leaf)
    n_children = len(child_specs)
    per_child = max(400, parent_words // n_children) if parent_words else LONG_LEAF_SPLIT_TARGET_PER_CHILD
    child_level = int(leaf.get("level") or 1) + 1
    parent_req_ids = list(leaf.get("requirement_ids") or [])
    inherited_folder = leaf.get("bound_folder")
    assigned_specs = _assign_requirement_ids(child_specs, parent_req_ids, requirements)

    leaf["is_leaf"] = 0
    leaf["writing_guidance"] = None
    leaf["requirement_ids"] = []
    leaf.pop("guidance_brief", None)
    leaf.pop("content_boundary", None)
    leaf.pop("target_words", None)

    new_children: list[dict] = []
    for idx, spec in enumerate(assigned_specs, start=1):
        # 始终按顺序编号，忽略 LLM / 调用方传入的 id_suffix，避免重复 id 静默丢节点
        cid = f"{leaf_id}.{idx}"
        new_children.append({
            "id": cid,
            "title": spec["title"],
            "parent_id": leaf_id,
            "level": child_level,
            "is_leaf": 1,
            "sort_order": (leaf.get("sort_order") or 0) + idx,
            "bound_folder": inherited_folder,
            "requirement_ids": list(spec.get("requirement_ids") or []),
            "guidance_brief": spec["guidance_brief"],
            "content_boundary": spec["content_boundary"],
            "writing_guidance": serialize_writing_guidance(
                brief=spec["guidance_brief"],
                content_boundary=spec["content_boundary"],
                target_words=per_child,
                split_origin=True,
            ),
        })

    merged = [n for n in nodes if str(n.get("id")) != leaf_id]
    merged.append(leaf)
    merged.extend(new_children)
    merged = _reorder_outline_nodes(merged)
    sanitized, _ = sanitize_leaf_content_boundaries(merged)
    return sanitized


def split_long_leaves(
    db: Session,
    project: Project,
    *,
    leaf_id: str | None = None,
    threshold: int | None = None,
) -> dict:
    rows = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project.id)
        .order_by(TechOutline.sort_order)
        .all()
    )
    if any(r.is_locked for r in rows):
        raise ValueError("大纲已锁定，无法拆分。请在大纲锁定前完成结构拆分。")

    nodes = _outline_rows_to_enrich_nodes(rows)
    global_info = _global_engineering_info(project)
    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id, TechRequirement.status == "confirmed")
        .all()
    )
    req_dicts = _req_dicts(requirements)
    split_req_dicts = _split_requirement_dicts(requirements)

    if leaf_id:
        targets = [leaf_id]
    else:
        targets = [str(n["id"]) for n in find_long_leaves(nodes, threshold=threshold)]

    split_count = 0
    skipped: list[dict] = []
    warnings: list[str] = []
    new_ids: list[str] = []
    current_nodes = nodes

    for tid in targets:
        node_map = {str(n["id"]): n for n in current_nodes}
        leaf = node_map.get(tid)
        if not leaf:
            skipped.append({"id": tid, "reason": "节点不存在"})
            continue
        ok, reason = is_splittable_leaf(leaf, threshold=threshold)
        if not ok:
            skipped.append({"id": tid, "title": leaf.get("title"), "reason": reason})
            continue
        try:
            child_specs, issues = call_structured_split(
                leaf, current_nodes, global_info, split_req_dicts,
            )
            if issues:
                skipped.append({
                    "id": tid,
                    "title": leaf.get("title"),
                    "reason": "；".join(issues[:2]),
                })
                warnings.append(f"「{leaf.get('title')}」拆分失败：{issues[0]}")
                continue
            updated = apply_leaf_split(
                current_nodes, tid, child_specs, requirements=split_req_dicts,
            )
            child_ids = [str(c["id"]) for c in updated if c.get("parent_id") == tid]
            current_nodes = updated
            split_count += 1
            new_ids.extend(child_ids)
            logger.info("结构拆分成功 leaf=%s -> %d 个子节点", tid, len(child_ids))
        except Exception as exc:
            skipped.append({"id": tid, "title": leaf.get("title"), "reason": str(exc)})
            warnings.append(f"「{leaf.get('title')}」拆分异常：{exc}")

    if split_count == 0 and not skipped:
        return {
            "success": True,
            "split_count": 0,
            "skipped": [],
            "warnings": [],
            "new_node_ids": [],
            "nodes": get_outline_tree(db, project.id),
            "message": "没有需要拆分的长章节",
        }

    target_pages = int(get_meta(project).get("target_pages") or TARGET_PAGES_DEFAULT)
    generation_mode = get_generation_mode(project)
    enriched = enrich_outline_nodes(
        current_nodes, req_dicts, target_pages, generation_mode=generation_mode,
    )
    save_outline_tree(db, project.id, enriched)

    split_warnings = list(get_meta(project).get("outline_warnings") or [])
    for w in warnings:
        if w not in split_warnings:
            split_warnings.append(w)
    set_meta(project, outline_warnings=split_warnings)

    message = f"已拆分 {split_count} 个长章节，新增 {len(new_ids)} 个子节点"
    if skipped:
        message += f"；跳过 {len(skipped)} 个"

    return {
        "success": True,
        "split_count": split_count,
        "skipped": skipped,
        "warnings": warnings,
        "new_node_ids": new_ids,
        "nodes": get_outline_tree(db, project.id),
        "message": message,
    }

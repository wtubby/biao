import json
import logging

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from db.models import Project, TechOutline, TechRequirement
from domains.registry import DEFAULT_DOMAIN, resolve_domain
from llm.llm_client import call_llm_json
from prompts.outline_prompt import (
    LEAF_GUIDANCE_SYSTEM_PROMPT,
    build_branch_user_prompt,
    build_leaf_guidance_user_prompt,
    build_skeleton_user_prompt,
    get_branch_system_prompt,
    get_reference_structure,
    get_skeleton_system_prompt,
)
from services.knowledge_registry import get_knowledge_folders
from services.project_meta import (
    get_meta,
    get_outline_catalog,
    get_outline_catalog_text,
    is_valid_outline_catalog,
    set_meta,
    set_outline_catalog,
)
from services.generation_mode import (
    GENERATION_MODE_FULL,
    get_generation_mode,
    scale_target_words,
)
from services.catalog_parser import parse_catalog_text
from config import TARGET_PAGES_DEFAULT, WORDS_PER_SCORE_PAGE
from services.generation_config import normalize_custom_total_words, resolve_target_pages
from services.writing_guidance import (
    default_content_boundary_for_title,
    get_chapter_type,
    guidance_to_outline_dict,
    is_descriptive_chapter,
    normalize_style_tier,
    parse_writing_guidance,
    serialize_writing_guidance,
)
from services.chapter_review_errors import parse_review_errors
from services.outline_boundary_rules import sanitize_leaf_content_boundaries
from services.prompt_project_info import (
    build_prompt_global_params,
    validate_prompt_global_params,
)
from services.outline_order import reorder_outline_dict_nodes, sort_outline_tree_dfs
from services.requirement_utils import requirement_dicts


def _req_dicts(requirements: list[TechRequirement]) -> list[dict]:
    return requirement_dicts(requirements)


def _global_engineering_info(project: Project) -> dict:
    return build_prompt_global_params(project)


def save_user_catalog(project: Project, text: str) -> list[dict]:
    catalog = parse_catalog_text(text)
    if not is_valid_outline_catalog(catalog):
        raise ValueError("目录格式无法识别，请至少填写 2 个章节标题。支持：（一）标题、第一章 标题、1. 标题 等格式")
    set_outline_catalog(project, text.strip(), catalog)
    return catalog


def get_user_catalog(project: Project) -> dict:
    return {
        "text": get_outline_catalog_text(project),
        "catalog": get_outline_catalog(project),
    }


def _validate_global_info(info: dict) -> None:
    validate_prompt_global_params(info)


def _match_requirements_for_title(title: str, requirements: list[dict]) -> list[str]:
    """分支展开失败时，按标题与评分项名称的包含关系猜测绑定。"""
    title_norm = (title or "").strip()
    if not title_norm:
        return []
    matched: list[str] = []
    for req in requirements:
        req_title = (req.get("title") or "").strip()
        if not req_title:
            continue
        if req_title in title_norm or title_norm in req_title:
            matched.append(req["id"])
            continue
        category = (req.get("score_category") or "").strip()
        if category and (category in title_norm or title_norm in category):
            matched.append(req["id"])
    return list(dict.fromkeys(matched))


def _guess_bound_folder(title: str, knowledge_folders: list[str]) -> str | None:
    title_norm = (title or "").strip()
    for folder in knowledge_folders:
        key = folder.replace("安装", "").replace("敷设", "").replace("调试", "")
        if key and key in title_norm:
            return folder
        if folder in title_norm:
            return folder
    return None


def _fallback_branch_leaf(
    branch: dict,
    requirements: list[dict],
    knowledge_folders: list[str],
) -> dict:
    title = branch.get("title") or "未命名章节"
    boundary = default_content_boundary_for_title(title) or (
        f"撰写「{title}」对应技术方案正文，回应相关评分项；不输出章节标题行。"
    )
    req_ids = _match_requirements_for_title(title, requirements)
    return {
        **branch,
        "is_leaf": 1,
        "requirement_ids": req_ids,
        "writing_guidance": f"撰写{title}技术内容",
        "content_boundary": boundary,
        "bound_folder": _guess_bound_folder(title, knowledge_folders),
    }


def _is_outline_node_stale(
    old: TechOutline | None,
    node: dict,
    req_ids: list[str],
    writing_guidance: str | None,
) -> bool:
    if not old:
        return False
    new_title = node.get("title") or "未命名章节"
    if (old.title or "") != new_title:
        return True
    old_req_ids: list[str] = []
    if old.requirement_ids:
        try:
            old_req_ids = json.loads(old.requirement_ids)
        except json.JSONDecodeError:
            pass
    if sorted(str(i) for i in old_req_ids) != sorted(str(i) for i in req_ids):
        return True
    if (old.writing_guidance or "") != (writing_guidance or ""):
        return True
    return False


def generate_outline_skeleton(
    global_info: dict,
    catalog: list[dict],
    reference_text: str,
    *,
    generation_mode: str = GENERATION_MODE_FULL,
) -> list[dict]:
    domain = (global_info or {}).get("工程领域")
    messages = [
        {"role": "system", "content": get_skeleton_system_prompt(domain)},
        {
            "role": "user",
            "content": build_skeleton_user_prompt(
                global_info, catalog, reference_text, generation_mode=generation_mode,
            ),
        },
    ]
    result = call_llm_json(
        messages,
        max_tokens=3000,
        timeout=90.0,
        max_retries=2,
        truncation_hint="你上次返回的骨架 JSON 被截断，请重新输出完整 JSON，减少每个一级章节下的二级子节数量。",
    )
    nodes = result.get("nodes") or []
    if not any(int(n.get("level") or 1) == 1 for n in nodes):
        raise ValueError("大纲骨架生成失败：未包含一级章节")
    return nodes


def _other_branches_for_expand(
    level2_nodes: list[dict],
    current_branch: dict,
) -> list[dict]:
    current_id = str(current_branch.get("id") or "")
    return [
        {"id": n["id"], "title": n.get("title"), "parent_id": n.get("parent_id")}
        for n in level2_nodes
        if str(n.get("id") or "") != current_id
    ]


def _expand_branch(
    global_info: dict,
    branch: dict,
    catalog: list[dict],
    requirements: list[dict],
    knowledge_folders: list[str],
    *,
    generation_mode: str = GENERATION_MODE_FULL,
    other_branches: list[dict] | None = None,
) -> list[dict]:
    domain = (global_info or {}).get("工程领域")
    messages = [
        {"role": "system", "content": get_branch_system_prompt(domain)},
        {
            "role": "user",
            "content": build_branch_user_prompt(
                global_info, branch, catalog, requirements, knowledge_folders,
                generation_mode=generation_mode,
                other_branches=other_branches,
            ),
        },
    ]
    result = call_llm_json(
        messages,
        max_tokens=3000,
        timeout=90.0,
        max_retries=2,
        truncation_hint="你上次返回的分支 JSON 被截断，请压缩 content_boundary 至 150 字以内，重新输出完整 JSON。",
    )
    return result.get("nodes") or []


def _is_id_under_branch(node_id: str, branch_id: str) -> bool:
    return node_id == branch_id or node_id.startswith(f"{branch_id}.")


def _next_child_id(parent_id: str, used_ids: set[str]) -> str:
    idx = 1
    while True:
        candidate = f"{parent_id}.{idx}"
        if candidate not in used_ids:
            return candidate
        idx += 1


def _sanitize_branch_expand_nodes(
    branch: dict,
    nodes: list[dict],
    *,
    used_ids: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """校验分支展开节点 id 是否归属本分支且全局唯一，必要时按 branch_id 重命名。"""
    if not nodes:
        return [], []

    branch_id = str(branch["id"])
    branch_title = str(branch.get("title") or branch_id)
    warnings: list[str] = []
    occupied = used_ids if used_ids is not None else set()

    if len(nodes) == 1 and str(nodes[0].get("id")) == branch_id:
        node = dict(nodes[0])
        node["id"] = branch_id
        if node.get("parent_id") is None:
            node["parent_id"] = branch.get("parent_id")
        occupied.add(branch_id)
        return [node], []

    id_remap: dict[str, str] = {}
    local_used = set(occupied)
    local_used.add(branch_id)
    result: list[dict] = []

    ordered = sorted(
        nodes,
        key=lambda n: (
            int(n.get("level") or 99),
            int(n.get("sort_order") or 0),
            str(n.get("id") or ""),
        ),
    )

    for raw in ordered:
        node = dict(raw)
        old_id = str(node.get("id") or "").strip()

        if old_id == branch_id:
            new_id = branch_id
        elif old_id and _is_id_under_branch(old_id, branch_id) and old_id not in local_used:
            new_id = old_id
        else:
            parent_id = node.get("parent_id")
            parent_new = branch_id
            if parent_id is not None and str(parent_id).strip():
                pid = str(parent_id).strip()
                parent_new = id_remap.get(pid, pid)
                if not _is_id_under_branch(parent_new, branch_id):
                    parent_new = branch_id
            new_id = _next_child_id(parent_new, local_used)
            if old_id and old_id != new_id:
                warnings.append(
                    f"分支「{branch_title}」节点 id「{old_id}」已修正为「{new_id}」"
                )
            elif not old_id:
                warnings.append(
                    f"分支「{branch_title}」存在空 id 节点，已命名为「{new_id}」"
                )

        if old_id and old_id != new_id:
            id_remap[old_id] = new_id
        local_used.add(new_id)
        node["id"] = new_id

        if new_id == branch_id:
            node["parent_id"] = branch.get("parent_id")
        else:
            pid = node.get("parent_id")
            if pid is None or not str(pid).strip():
                node["parent_id"] = branch_id
            else:
                pid_str = str(pid).strip()
                mapped = id_remap.get(pid_str, pid_str)
                if mapped in local_used and _is_id_under_branch(mapped, branch_id):
                    node["parent_id"] = mapped
                elif mapped == branch_id:
                    node["parent_id"] = branch_id
                else:
                    node["parent_id"] = branch_id

        result.append(node)

    occupied.update(local_used)
    return result, warnings


def _ensure_unique_outline_ids(nodes: list[dict]) -> tuple[list[dict], list[str]]:
    """全树 id 唯一性兜底，防止跨分支残留冲突导致落库主键冲突。"""
    warnings: list[str] = []
    seen: set[str] = set()
    id_remap: dict[str, str] = {}
    result: list[dict] = []

    for raw in nodes:
        node = dict(raw)
        nid = str(node.get("id") or "").strip()
        if not nid:
            nid = f"outline-{len(result) + 1}"

        if nid in seen:
            parent = node.get("parent_id")
            if parent and str(parent) in seen:
                new_id = _next_child_id(str(parent), seen)
            else:
                suffix = 2
                new_id = f"{nid}-r{suffix}"
                while new_id in seen:
                    suffix += 1
                    new_id = f"{nid}-r{suffix}"
            warnings.append(f"节点 id「{nid}」与其他章节冲突，已重命名为「{new_id}」")
            id_remap[nid] = new_id
            nid = new_id

        seen.add(nid)
        node["id"] = nid
        result.append(node)

    for node in result:
        pid = node.get("parent_id")
        if pid is not None and str(pid) in id_remap:
            node["parent_id"] = id_remap[str(pid)]

    return result, warnings


def generate_outline_ai(db: Session, project: Project) -> tuple[list[TechOutline], str, list[str]]:
    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id, TechRequirement.status == "confirmed")
        .all()
    )
    # 评分项仅作参考：无已确认评分项时仍可按目录 + 工程信息深化大纲

    global_info = _global_engineering_info(project)
    _validate_global_info(global_info)

    catalog = get_outline_catalog(project)
    if not is_valid_outline_catalog(catalog):
        raise ValueError("请先填写并保存目录大纲，再进行 AI 深化")

    project_type = global_info.get("项目类型")
    engineering_domain = global_info.get("工程领域") or DEFAULT_DOMAIN
    knowledge_folders = get_knowledge_folders(project_type, engineering_domain)
    reference_text = get_reference_structure(project_type, engineering_domain)
    req_dicts = _req_dicts(requirements)
    generation_mode = get_generation_mode(project)

    logger.info(
        "大纲深化第一步：生成骨架（项目 %s，档位 %s，评分项 %d）",
        project.id, generation_mode, len(req_dicts),
    )
    skeleton_nodes = generate_outline_skeleton(
        global_info, catalog, reference_text, generation_mode=generation_mode,
    )
    level1_nodes = [n for n in skeleton_nodes if int(n.get("level") or 1) == 1]
    level2_nodes = [n for n in skeleton_nodes if int(n.get("level") or 1) == 2]
    if not level2_nodes:
        raise ValueError("大纲骨架生成失败：未包含任何二级章节，请重试")

    all_nodes: list[dict] = list(level1_nodes)
    occupied_ids: set[str] = {str(n["id"]) for n in level1_nodes}
    expand_warnings: list[str] = []
    node_warnings: dict[str, str] = {}
    logger.info("大纲深化第二步：逐支展开（共 %d 个分支）", len(level2_nodes))
    for branch in level2_nodes:
        branch_id = branch["id"]
        branch_title = branch.get("title") or "未命名章节"
        try:
            result_nodes = _expand_branch(
                global_info, branch, catalog, req_dicts, knowledge_folders,
                generation_mode=generation_mode,
                other_branches=_other_branches_for_expand(level2_nodes, branch),
            )
        except Exception as exc:
            logger.warning("分支「%s」展开失败，降级为单一叶子节点: %s", branch_title, exc)
            result_nodes = []
            warning_msg = (
                f"分支「{branch_title}」AI 展开失败（{exc}），已降级为单叶子节点，请人工检查写作指导与评分项绑定"
            )
            expand_warnings.append(warning_msg)
            node_warnings[branch_id] = warning_msg

        if result_nodes:
            result_nodes, id_warnings = _sanitize_branch_expand_nodes(
                branch, result_nodes, used_ids=occupied_ids,
            )
            expand_warnings.extend(id_warnings)

        if not result_nodes:
            if branch_id not in node_warnings:
                warning_msg = (
                    f"分支「{branch_title}」未生成子节点，已降级为单叶子节点，请人工检查写作指导与评分项绑定"
                )
                expand_warnings.append(warning_msg)
                node_warnings[branch_id] = warning_msg
            all_nodes.append(_fallback_branch_leaf(branch, req_dicts, knowledge_folders))
            occupied_ids.add(str(branch_id))
        elif any(n.get("id") == branch_id for n in result_nodes):
            all_nodes.extend(result_nodes)
        else:
            all_nodes.append({**branch, "is_leaf": 0})
            occupied_ids.add(str(branch_id))
            all_nodes.extend(result_nodes)

    all_nodes, dup_warnings = _ensure_unique_outline_ids(all_nodes)
    expand_warnings.extend(dup_warnings)

    target_pages = resolve_target_pages(
        get_meta(project).get("target_pages"),
        default=TARGET_PAGES_DEFAULT,
    )
    nodes = enrich_outline_nodes(
        all_nodes,
        req_dicts,
        target_pages,
        generation_mode=generation_mode,
        boundary_warnings=expand_warnings,
    )
    node_warnings = _merge_quality_warnings_to_nodes(nodes, expand_warnings, node_warnings)
    set_meta(
        project,
        outline_warnings=expand_warnings,
        outline_node_warnings=node_warnings,
    )
    outlines = save_outline_tree(db, project.id, nodes)
    return outlines, "user_catalog", expand_warnings


def enrich_outline_nodes(
    nodes: list[dict],
    requirements: list[dict],
    target_pages: int = TARGET_PAGES_DEFAULT,
    *,
    generation_mode: str = GENERATION_MODE_FULL,
    boundary_warnings: list[str] | None = None,
) -> list[dict]:
    """为叶子节点合并 content_boundary、计算 target_words 并序列化 writing_guidance。"""
    req_map = {r["id"]: r for r in requirements}
    total_score = sum(float(r.get("score_value") or 0) for r in requirements)
    total_budget_words = int(target_pages * WORDS_PER_SCORE_PAGE)

    # 同一评分项可能绑定到多个叶子：其字数预算按绑定叶子数均分，避免重复累加超页。
    req_leaf_count: dict[str, int] = {}
    for n in nodes:
        if not n.get("is_leaf"):
            continue
        seen: set[str] = set()
        for rid in n.get("requirement_ids") or []:
            if rid in req_map and rid not in seen:
                seen.add(rid)
                req_leaf_count[rid] = req_leaf_count.get(rid, 0) + 1

    def _allocated_words(n: dict) -> int:
        words = 0
        seen: set[str] = set()
        for rid in n.get("requirement_ids") or []:
            if rid in seen or rid not in req_map:
                continue
            seen.add(rid)
            score = float(req_map[rid].get("score_value") or 0)
            if total_score <= 0 or score <= 0:
                continue
            share = max(1, req_leaf_count.get(rid, 1))
            words += int(round(score / total_score * total_budget_words / share))
        return words

    # 有评分绑定的叶子先按分值占比切走预算；未绑定叶子只能从剩余预算均分，
    # 避免再拿全量 target_pages 重切一份导致总篇幅系统性超页。
    scored_leaf_words_total = 0
    unscored_leaf_count = 0
    for n in nodes:
        if not n.get("is_leaf"):
            continue
        allocated = _allocated_words(n)
        if allocated > 0:
            scored_leaf_words_total += allocated
        else:
            unscored_leaf_count += 1

    remaining_words = max(0, total_budget_words - scored_leaf_words_total)
    if unscored_leaf_count > 0:
        share = int(round(remaining_words / unscored_leaf_count))
        # 剩余预算足够时保底 400；不足时按实际剩余均分（可为 0），避免保底导致系统性超页
        if remaining_words >= 400 * unscored_leaf_count:
            unscored_base_words = max(400, share)
        else:
            unscored_base_words = max(0, share)
    else:
        unscored_base_words = 0

    enriched: list[dict] = []
    for node in nodes:
        item = dict(node)
        if not item.get("is_leaf"):
            item["writing_guidance"] = None
            enriched.append(item)
            continue

        allocated = _allocated_words(item)
        target_words = None
        if allocated > 0:
            target_words = scale_target_words(allocated, generation_mode)
        elif unscored_leaf_count > 0:
            target_words = scale_target_words(unscored_base_words, generation_mode)

        brief = str(item.get("guidance_brief") or "").strip()
        boundary = str(item.get("content_boundary") or "").strip()
        style_tier = normalize_style_tier(item.get("style_tier"))
        wg_raw = item.get("writing_guidance")
        split_origin = False
        if isinstance(wg_raw, str) and wg_raw.strip().startswith("{"):
            parsed = parse_writing_guidance(wg_raw)
            split_origin = bool(parsed.get("split_origin"))
            if not brief:
                brief = parsed["brief"]
            if not boundary:
                boundary = parsed["content_boundary"]
            if not item.get("style_tier"):
                style_tier = parsed["style_tier"]
        elif not brief:
            brief = str(wg_raw or "").strip()

        item["writing_guidance"] = serialize_writing_guidance(
            brief=brief,
            content_boundary=boundary,
            target_words=target_words,
            split_origin=split_origin,
            style_tier=style_tier,
        )
        item["style_tier"] = style_tier
        item.pop("content_boundary", None)
        enriched.append(item)

    enriched, bw = sanitize_leaf_content_boundaries(enriched)
    if boundary_warnings is not None:
        boundary_warnings.extend(bw)
    return enriched


def save_outline_tree(db: Session, project_id: str, nodes: list[dict]) -> list[TechOutline]:
    nodes = reorder_outline_dict_nodes(nodes)
    existing = {
        r.id: r
        for r in db.query(TechOutline).filter(TechOutline.project_id == project_id).all()
    }
    project_locked = any(r.is_locked for r in existing.values())
    db.query(TechOutline).filter(TechOutline.project_id == project_id).delete(
        synchronize_session="evaluate"
    )
    db.flush()

    outlines: list[TechOutline] = []
    for i, node in enumerate(nodes):
        req_ids = node.get("requirement_ids") or []
        node_id = str(node.get("id") or f"ch-{i + 1}")
        old = existing.get(node_id)
        writing_guidance = None
        if node.get("is_leaf"):
            wg_raw = node.get("writing_guidance")
            parsed = parse_writing_guidance(wg_raw if isinstance(wg_raw, str) else None)
            boundary = str(node.get("content_boundary") or parsed["content_boundary"] or "").strip()
            brief = str(node.get("guidance_brief") or parsed["brief"] or "").strip()
            target_words = parsed["target_words"]
            style_tier = normalize_style_tier(node.get("style_tier") or parsed.get("style_tier"))
            writing_guidance = serialize_writing_guidance(
                brief=brief,
                content_boundary=boundary,
                target_words=target_words,
                split_origin=bool(parsed.get("split_origin")),
                style_tier=style_tier,
            )

        stale = _is_outline_node_stale(old, node, req_ids, writing_guidance)
        preserved_content = None if stale else (old.generated_content if old else None)
        preserved_summary = None if stale else (old.last_summary if old else None)
        preserved_status = "init" if stale else (old.review_status if old else "init")

        outline = TechOutline(
            id=node_id,
            project_id=project_id,
            title=node.get("title") or "未命名章节",
            parent_id=node.get("parent_id"),
            sort_order=int(node.get("sort_order") or i + 1),
            level=int(node.get("level") or 1),
            is_leaf=1 if node.get("is_leaf") else 0,
            bound_folder=node.get("bound_folder"),
            requirement_ids=json.dumps(req_ids, ensure_ascii=False),
            writing_guidance=writing_guidance,
            is_locked=1 if project_locked or (old.is_locked if old else 0) else 0,
            generated_content=preserved_content,
            last_summary=preserved_summary,
            review_status=preserved_status,
            review_errors=None if stale else (old.review_errors if old else None),
            retry_count=0 if stale else (old.retry_count if old else 0),
            content_plan=None if stale else (old.content_plan if old else None),
            prompt_debug=None if stale else (old.prompt_debug if old else None),
            generated_at=None if stale else (old.generated_at if old else None),
        )
        db.add(outline)
        outlines.append(outline)

    db.commit()
    return outlines


def _merge_quality_warnings_to_nodes(
    nodes: list[dict],
    warnings: list[str],
    node_warnings: dict[str, str],
) -> dict[str, str]:
    """将章节级质量警告（如 content_boundary 门禁）挂到对应节点。"""
    merged = dict(node_warnings)
    for node in nodes:
        if not node.get("is_leaf"):
            continue
        node_id = str(node.get("id") or "")
        title = str(node.get("title") or "").strip()
        if not node_id or not title:
            continue
        for warning in warnings:
            if f"章节「{title}」" in warning and node_id not in merged:
                merged[node_id] = warning
                break
    return merged


def get_outline_warnings(project: Project | None) -> list[str]:
    if not project:
        return []
    raw = get_meta(project).get("outline_warnings") or []
    return [str(w) for w in raw] if isinstance(raw, list) else []


def get_outline_tree(db: Session, project_id: str) -> list[dict]:
    project = db.query(Project).filter(Project.id == project_id).first()
    node_warnings: dict[str, str] = {}
    if project:
        node_warnings = get_meta(project).get("outline_node_warnings") or {}
    rows = sort_outline_tree_dfs(
        db.query(TechOutline).filter(TechOutline.project_id == project_id).all()
    )
    return [_outline_to_dict(r, node_warnings) for r in rows]


def _outline_to_dict(row: TechOutline, node_warnings: dict[str, str] | None = None) -> dict:
    req_ids = []
    if row.requirement_ids:
        try:
            req_ids = json.loads(row.requirement_ids)
        except json.JSONDecodeError:
            pass
    debug = None
    if row.prompt_debug:
        # 延迟导入，避免与 prompt_debug_service 循环依赖
        from services.prompt_debug_service import parse_stored_prompt_debug
        debug = parse_stored_prompt_debug(row.prompt_debug)
    base = {
        "id": row.id,
        "project_id": row.project_id,
        "title": row.title,
        "parent_id": row.parent_id,
        "sort_order": row.sort_order,
        "level": row.level,
        "is_leaf": row.is_leaf,
        "bound_folder": row.bound_folder,
        "requirement_ids": req_ids,
        "generated_content": row.generated_content,
        "last_summary": row.last_summary,
        "is_locked": row.is_locked,
        "review_status": row.review_status,
        "review_errors": parse_review_errors(row.review_errors),
        "retry_count": row.retry_count,
        "prompt_debug": debug,
    }
    base.update(guidance_to_outline_dict(row.writing_guidance))
    if debug and debug.get("retrieval_warning"):
        base["retrieval_warning"] = debug["retrieval_warning"]
    if debug and debug.get("retrieval_route"):
        base["retrieval_route"] = debug["retrieval_route"]
    if node_warnings:
        warning = node_warnings.get(row.id)
        if warning:
            base["expand_degraded"] = True
            base["expand_warning"] = warning
    base["chapter_type"] = get_chapter_type(row.title)
    return base


def validate_coverage(db: Session, project_id: str) -> dict:
    outlines = db.query(TechOutline).filter(TechOutline.project_id == project_id).all()
    requirements = db.query(TechRequirement).filter(TechRequirement.project_id == project_id).all()

    covered: set[str] = set()
    unbound_leaves: list[str] = []
    optional_unbound_leaves: list[str] = []
    for node in outlines:
        if node.is_leaf != 1:
            continue
        req_ids = []
        if node.requirement_ids:
            try:
                req_ids = json.loads(node.requirement_ids)
            except json.JSONDecodeError:
                pass
        if not req_ids:
            label = f"{node.id} {node.title}"
            if is_descriptive_chapter(node.title):
                optional_unbound_leaves.append(label)
            else:
                unbound_leaves.append(label)
        covered.update(req_ids)

    risk_ids = {r.id for r in requirements if r.is_risk_item == 1}
    uncovered_risk = risk_ids - covered
    risk_titles = {r.id: r.requirement_title for r in requirements if r.id in uncovered_risk}

    confirmed_ids = {r.id for r in requirements if r.status == "confirmed"}
    uncovered_confirmed = confirmed_ids - covered
    req_titles = {r.id: r.requirement_title for r in requirements}

    leaves = [o for o in outlines if o.is_leaf == 1]
    from services.generation_config import get_generation_config

    project = db.query(Project).filter(Project.id == project_id).first()
    require_risk = True
    if project:
        require_risk = bool(get_generation_config(project).get("require_risk_binding", True))

    uncovered_risk_list = [{"id": k, "title": risk_titles[k]} for k in uncovered_risk]
    uncovered_req_list = [
        {
            "id": k,
            "title": req_titles[k],
            "score_value": next((r.score_value for r in requirements if r.id == k), None),
        }
        for k in uncovered_confirmed
    ]
    # 刚性风险项未绑定：可开关强制；其余评分项仍为建议性提示
    has_advisory_gaps = bool(uncovered_req_list or unbound_leaves)
    blocking_risk = bool(require_risk and uncovered_risk_list)
    passed = bool(leaves) and not blocking_risk
    return {
        "passed": passed,
        "has_advisory_gaps": has_advisory_gaps,
        "require_risk_binding": require_risk,
        "uncovered_risk_items": uncovered_risk_list,
        "uncovered_requirements": uncovered_req_list,
        "unbound_leaves": unbound_leaves,
        "optional_unbound_leaves": optional_unbound_leaves,
        "message": (
            "存在未绑定的刚性风险评分项，请先绑定章节或在生成配置中关闭「刚性项必须绑定」"
            if blocking_risk
            else None
        ),
    }


def lock_outline(db: Session, project_id: str) -> None:
    outlines = db.query(TechOutline).filter(TechOutline.project_id == project_id).all()
    if not outlines:
        raise ValueError("请先生成大纲后再锁定")
    leaves = [o for o in outlines if o.is_leaf == 1]
    if not leaves:
        raise ValueError("大纲中没有可生成的叶子章节，请先完善大纲")

    coverage = validate_coverage(db, project_id)
    if not coverage.get("passed"):
        raise ValueError(
            coverage.get("message")
            or "大纲覆盖校验未通过：请先绑定刚性风险评分项，或在生成配置中关闭「刚性项必须绑定」"
        )

    for row in outlines:
        row.is_locked = 1
    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.status = "outline_locked"
    db.commit()


def _outline_rows_to_enrich_nodes(rows: list[TechOutline]) -> list[dict]:
    nodes: list[dict] = []
    for row in rows:
        req_ids: list[str] = []
        if row.requirement_ids:
            try:
                req_ids = json.loads(row.requirement_ids)
            except json.JSONDecodeError:
                pass
        parsed = parse_writing_guidance(row.writing_guidance)
        nodes.append({
            "id": row.id,
            "title": row.title,
            "parent_id": row.parent_id,
            "sort_order": row.sort_order,
            "level": row.level,
            "is_leaf": row.is_leaf,
            "bound_folder": row.bound_folder,
            "requirement_ids": req_ids,
            "guidance_brief": parsed["brief"],
            "content_boundary": parsed["content_boundary"],
            "writing_guidance": row.writing_guidance,
            "style_tier": parsed["style_tier"],
        })
    return nodes


def regenerate_leaf_guidance(
    db: Session,
    project: Project,
    leaf_id: str,
    *,
    style_tier: str | None = None,
) -> dict:
    """为单个叶子节点重新生成写作要点与内容边界，保留绑定与目标字数。"""
    row = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project.id, TechOutline.id == leaf_id)
        .first()
    )
    if not row:
        raise ValueError("章节不存在")
    if int(row.is_leaf or 0) != 1:
        raise ValueError("仅叶子章节可重新生成编写思路")

    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id, TechRequirement.status == "confirmed")
        .all()
    )
    req_dicts = _req_dicts(requirements)
    parsed = parse_writing_guidance(row.writing_guidance)
    req_ids = []
    if row.requirement_ids:
        try:
            req_ids = json.loads(row.requirement_ids)
        except json.JSONDecodeError:
            pass
    leaf = {
        "id": row.id,
        "title": row.title,
        "requirement_ids": req_ids,
        "guidance_brief": parsed["brief"],
        "content_boundary": parsed["content_boundary"],
        "style_tier": normalize_style_tier(style_tier or parsed.get("style_tier")),
    }
    global_info = _global_engineering_info(project)
    result = call_llm_json(
        [
            {"role": "system", "content": LEAF_GUIDANCE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_leaf_guidance_user_prompt(
                    global_info, leaf, req_dicts, style_tier=leaf["style_tier"],
                ),
            },
        ]
    )
    if not isinstance(result, dict):
        raise ValueError("AI 返回格式无效")
    brief = str(
        result.get("writing_guidance")
        or result.get("guidance_brief")
        or result.get("brief")
        or ""
    ).strip()
    boundary = str(result.get("content_boundary") or "").strip()
    if not brief and not boundary:
        raise ValueError("AI 未返回有效的编写思路")

    writing_guidance = serialize_writing_guidance(
        brief=brief or parsed["brief"],
        content_boundary=boundary or parsed["content_boundary"],
        target_words=parsed.get("target_words"),
        split_origin=bool(parsed.get("split_origin")),
        style_tier=leaf["style_tier"],
    )
    row.writing_guidance = writing_guidance
    db.commit()
    db.refresh(row)
    return _outline_to_dict(row)


def reapply_outline_generation_mode(db: Session, project: Project) -> int:
    """切换档位/篇幅后，按当前大纲结构重算各章目标字数。

    只原地更新 writing_guidance，不走 save_outline_tree，避免 target_words
    变化被判 stale 而清空已生成正文。
    """
    rows = sort_outline_tree_dfs(
        db.query(TechOutline).filter(TechOutline.project_id == project.id).all()
    )
    if not rows:
        return 0

    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id, TechRequirement.status == "confirmed")
        .all()
    )
    req_dicts = _req_dicts(requirements)
    target_pages = resolve_target_pages(
        get_meta(project).get("target_pages"),
        default=TARGET_PAGES_DEFAULT,
    )
    generation_mode = get_generation_mode(project)
    nodes = _outline_rows_to_enrich_nodes(rows)
    enriched = enrich_outline_nodes(
        nodes, req_dicts, target_pages, generation_mode=generation_mode,
    )
    enriched_by_id = {str(n.get("id")): n for n in enriched}
    for row in rows:
        if not row.is_leaf:
            continue
        node = enriched_by_id.get(row.id)
        if not node:
            continue
        wg_raw = node.get("writing_guidance")
        parsed = parse_writing_guidance(wg_raw if isinstance(wg_raw, str) else None)
        boundary = str(node.get("content_boundary") or parsed["content_boundary"] or "").strip()
        brief = str(node.get("guidance_brief") or parsed["brief"] or "").strip()
        style_tier = normalize_style_tier(node.get("style_tier") or parsed.get("style_tier"))
        row.writing_guidance = serialize_writing_guidance(
            brief=brief,
            content_boundary=boundary,
            target_words=parsed["target_words"],
            split_origin=bool(parsed.get("split_origin")),
            style_tier=style_tier,
        )
    db.flush()
    return len(rows)


def scale_leaves_to_total_words(db: Session, project: Project, total_words: int) -> int:
    """按自定义总字数等比缩放叶子 target_words，保留已生成正文。"""
    clamped = normalize_custom_total_words(total_words)
    if clamped is None:
        return 0
    total_words = clamped
    rows = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project.id, TechOutline.is_leaf == 1)
        .all()
    )
    if not rows or total_words <= 0:
        return 0
    current = 0
    parsed_by_id: dict[str, dict] = {}
    for row in rows:
        parsed = parse_writing_guidance(row.writing_guidance)
        parsed_by_id[row.id] = parsed
        current += int(parsed.get("target_words") or 0)
    if current <= 0:
        return 0
    ratio = total_words / current
    for row in rows:
        parsed = parsed_by_id[row.id]
        base = int(parsed.get("target_words") or 0)
        if base > 0:
            scaled = max(200, int(round(base * ratio)))
            row.writing_guidance = serialize_writing_guidance(
                brief=parsed["brief"],
                content_boundary=parsed["content_boundary"],
                target_words=scaled,
                split_origin=bool(parsed.get("split_origin")),
                style_tier=parsed.get("style_tier"),
            )
    db.flush()
    return len(rows)

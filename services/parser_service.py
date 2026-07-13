import logging
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from db.models import Project, TechRequirement
from llm.llm_client import call_llm_json
from prompts.extraction_prompt import build_extraction_user_prompt, get_extraction_system_prompt
from services.blind_bid_service import detect_blind_bid
from services.document_parser import ParsedContent, ParsedItem, parse_document
from services.facts_service import prefill_facts_from_extraction
from services.project_meta import (
    PARSE_STAGE_DONE,
    PARSE_STAGE_ERROR,
    PARSE_STAGE_EXTRACTING,
    PARSE_STAGE_READING,
    PARSE_STAGE_SAVING,
    set_meta,
    set_parse_error,
    set_parse_progress,
)
from services.bid_reference_catalog_extractor import extract_bid_reference_catalog_from_items
from services.tender_detail_service import (
    _is_manually_confirmed,
    empty_tender_detail,
    get_tender_detail,
    merge_tender_detail,
    save_tender_detail_from_extraction,
    set_tender_detail,
)

logger = logging.getLogger(__name__)

MAX_TABLE_CHARS = 30000
MAX_PARA_CHARS = 20000
CHUNK_PAGE_SIZE = 15
# 单块送入 LLM 的正文预算（表+段合计），避免整本挤进一块后被截断丢掉文末「投标文件格式」
CHUNK_MAX_CHARS = 18000
BLIND_BID_DETECT_WARNING = "检测到本项目可能为暗标，请确认「暗标」开关"

EXTRACTION_TRUNCATION_HINT = (
    "你上次返回的 JSON 无效或被截断。请重新输出完整 JSON："
    "1) 字符串内换行用 \\n、双引号用 \\\" 转义；"
    "2) requirements 数组不得省略条目；"
    "3) 长字段可精简 source_text 为关键句，但须保留评分项完整性。"
)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n... [内容已截断]"


def _annotate_pages(items: list[ParsedItem], kind: str) -> str:
    """在每段正文前标注真实页码，供 LLM 填写 source_page。"""
    parts = [f"[第{i.page}页]\n{i.text}" for i in items if i.kind == kind]
    combined = "\n\n---\n\n".join(parts)
    max_len = MAX_TABLE_CHARS if kind == "table" else MAX_PARA_CHARS
    return _truncate(combined, max_len) if combined else (
        "（无表格内容）" if kind == "table" else "（无段落内容）"
    )


def _chunk_by_pages(items: list[ParsedItem], chunk_page_size: int) -> list[list[ParsedItem]]:
    if not items:
        return []
    max_page = max(i.page for i in items)
    chunks: list[list[ParsedItem]] = []
    for start in range(1, max_page + 1, chunk_page_size):
        end = start + chunk_page_size - 1
        chunk = [i for i in items if start <= i.page <= end]
        if chunk:
            chunks.append(chunk)
    return chunks


def _item_char_weight(item: ParsedItem) -> int:
    return len((item.text or "").strip())


def _split_chunk_by_chars(
    items: list[ParsedItem],
    max_chars: int = CHUNK_MAX_CHARS,
) -> list[list[ParsedItem]]:
    """将过长块再按字数切开，保证文末章节也能进入后续 LLM 分段。"""
    if not items:
        return []
    if sum(_item_char_weight(i) for i in items) <= max_chars:
        return [items]

    chunks: list[list[ParsedItem]] = []
    current: list[ParsedItem] = []
    current_chars = 0
    for item in items:
        weight = _item_char_weight(item)
        if current and current_chars + weight > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += weight
        # 单条超长时仍单独成块，交由 _annotate_pages 截断
        if current_chars >= max_chars and len(current) == 1:
            chunks.append(current)
            current = []
            current_chars = 0
    if current:
        chunks.append(current)
    return chunks


def _chunk_for_extraction(
    items: list[ParsedItem],
    chunk_page_size: int = CHUNK_PAGE_SIZE,
    max_chars: int = CHUNK_MAX_CHARS,
) -> list[list[ParsedItem]]:
    """页码分块 + 字数再切：docx 常把全文标成第 1 页，仅按页会把文末格式章裁掉。"""
    if not items:
        return []
    pages = {i.page for i in items}
    if len(pages) <= 1:
        return _split_chunk_by_chars(items, max_chars=max_chars)

    result: list[list[ParsedItem]] = []
    for page_chunk in _chunk_by_pages(items, chunk_page_size):
        result.extend(_split_chunk_by_chars(page_chunk, max_chars=max_chars))
    return result


def _chunk_page_hint(chunk: list[ParsedItem], chunk_index: int, chunk_total: int) -> str:
    if not chunk:
        return f"分段{chunk_index}/{chunk_total}"
    pages = sorted({i.page for i in chunk})
    if len(pages) == 1 and chunk_total > 1 and pages[0] == 1:
        return f"全文分段{chunk_index}/{chunk_total}"
    if len(pages) == 1:
        return f"第{pages[0]}页"
    return f"第{pages[0]}-{pages[-1]}页"


def _ensure_bid_reference_catalog(result: dict, items: list[ParsedItem]) -> None:
    """LLM 未抽出参考格式时，用全文启发式回填（不依赖截断后的 prompt）。"""
    detail = result.setdefault("tender_detail", empty_tender_detail())
    if not isinstance(detail, dict):
        detail = empty_tender_detail()
        result["tender_detail"] = detail
    current = str(detail.get("bid_reference_catalog") or "").strip()
    if current:
        return
    fallback = extract_bid_reference_catalog_from_items(items)
    if fallback:
        detail["bid_reference_catalog"] = fallback
        logger.info("已用启发式回填 bid_reference_catalog（%d 字）", len(fallback))


def _extract_single_chunk(items: list[ParsedItem], page_hint: str | None = None) -> dict:
    user_content = build_extraction_user_prompt(
        _annotate_pages(items, "table"),
        _annotate_pages(items, "paragraph"),
    )
    if page_hint:
        user_content += f"\n\n（本段原文范围：{page_hint}）"

    messages = [
        {"role": "system", "content": get_extraction_system_prompt()},
        {"role": "user", "content": user_content},
    ]
    return call_llm_json(
        messages,
        max_tokens=12000,
        truncation_hint=EXTRACTION_TRUNCATION_HINT,
    )


def extract_with_llm(
    parsed: ParsedContent,
    on_chunk: Callable[[int, int, str], None] | None = None,
) -> dict:
    """分块提取 + 合并，替代原单次超长提取。

    on_chunk(chunk_index, chunk_total, page_hint) 在每块 LLM 调用前触发（1-based index）。
    """
    chunks = _chunk_for_extraction(parsed.items, CHUNK_PAGE_SIZE, CHUNK_MAX_CHARS)

    if len(chunks) <= 1:
        if on_chunk:
            on_chunk(1, 1, "全文")
        result = _extract_single_chunk(parsed.items)
        _ensure_bid_reference_catalog(result, parsed.items)
        return result

    merged: dict = {
        "global_params": {},
        "contradictions": [],
        "requirements": [],
        "fact_groups": [],
        "tender_detail": empty_tender_detail(),
    }
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        page_range = _chunk_page_hint(chunk, idx, total)
        if on_chunk:
            on_chunk(idx, total, page_range)
        result = _extract_single_chunk(chunk, page_hint=page_range)

        for key, value in (result.get("global_params") or {}).items():
            if value and not merged["global_params"].get(key):
                merged["global_params"][key] = value

        merged["contradictions"].extend(result.get("contradictions") or [])
        merged["requirements"].extend(result.get("requirements") or [])
        _merge_fact_groups(merged["fact_groups"], result.get("fact_groups") or [])
        merge_tender_detail(merged["tender_detail"], result.get("tender_detail") or {})

    _ensure_bid_reference_catalog(merged, parsed.items)
    return merged


def _merge_fact_groups(target: list[dict], incoming: list[dict]) -> None:
    titles = {str(item.get("title") or "").strip() for item in target}
    for item in incoming:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if not title or not content or title in titles:
            continue
        target.append({"title": title, "content": content})
        titles.add(title)


def _parsed_full_text(parsed: ParsedContent) -> str:
    return "\n".join(item.text for item in parsed.items if (item.text or "").strip())


def apply_blind_bid_detection(project: Project, full_text: str) -> bool:
    """关键词命中则预勾选暗标；未命中保持原值（None/LLM 结果），不直接判 False。"""
    if detect_blind_bid(full_text) is not True:
        set_meta(project, blind_bid_auto_detected=False)
        return False
    detail = get_tender_detail(project)
    notice = detail.setdefault("notice", empty_tender_detail()["notice"])
    notice["blind_bid"] = True
    set_tender_detail(project, detail)
    set_meta(project, blind_bid_auto_detected=True)
    return True


def _is_duplicate_title(title: str, seen: list[str], threshold: float = 0.9) -> bool:
    norm = (title or "").strip().lower()
    if not norm:
        return False
    for existing in seen:
        if SequenceMatcher(None, norm, existing).ratio() >= threshold:
            return True
    return False


def compute_parse_confidence(
    parsed: ParsedContent,
    result: dict,
    requirements: list[TechRequirement],
) -> dict:
    """根据文档解析与 LLM 提取结果估算可信度（0~1）。"""
    warnings: list[str] = []
    doc_score = 0.0

    if parsed.error or not parsed.items:
        warnings.append("未能从文档中提取有效文本层")
    else:
        doc_score += 0.12
        if parsed.page_count > 0:
            doc_score += 0.04
        if parsed.tables:
            doc_score += 0.05
        else:
            warnings.append("未识别到表格内容，评分项可能不完整")
        if len(parsed.paragraphs) >= 5:
            doc_score += 0.04
        else:
            warnings.append("文档段落较少，解析基础偏弱")
        if parsed.is_scanned:
            warnings.append("疑似扫描件，OCR 结果可能影响提取准确度")
            doc_score = max(0.0, doc_score - 0.05)

    req_score = 0.0
    if not requirements:
        warnings.append("未提取到技术评分项")
    else:
        total = len(requirements)
        with_page = sum(1 for req in requirements if req.source_page)
        with_score = sum(1 for req in requirements if req.score_value is not None)
        with_source = sum(1 for req in requirements if (req.source_text or "").strip())

        req_score += 0.18
        if with_page / total >= 0.5:
            req_score += 0.1
        else:
            warnings.append(f"仅 {with_page}/{total} 个评分项标注了来源页码")
        if with_score / total >= 0.7:
            req_score += 0.12
        else:
            warnings.append(f"有 {total - with_score} 个评分项缺少分值")
        if with_source / total >= 0.8:
            req_score += 0.1
        else:
            warnings.append("部分评分项缺少原文摘录，请人工核对")

    global_params = result.get("global_params") or {}
    from domains.registry import DEFAULT_DOMAIN, resolve_domain
    domain_key = resolve_domain(global_params.get("engineering_domain")).key
    required_keys = ["name", "project_type", "location", "duration_days"]
    if domain_key == DEFAULT_DOMAIN:
        required_keys = ["name", "project_type", "voltage_level", "location", "duration_days"]
    filled = sum(1 for key in required_keys if global_params.get(key))
    gp_score = (filled / len(required_keys)) * 0.2
    if filled < max(2, len(required_keys) - 2):
        warnings.append("全局工程参数提取不完整，请人工补充")

    confidence = round(min(1.0, doc_score + req_score + gp_score), 2)
    if confidence >= 0.75:
        level = "high"
    elif confidence >= 0.5:
        level = "medium"
    else:
        level = "low"

    return {
        "confidence": confidence,
        "level": level,
        "warnings": warnings,
        "stats": {
            "page_count": parsed.page_count,
            "table_count": len(parsed.tables),
            "paragraph_count": len(parsed.paragraphs),
            "requirement_count": len(requirements),
            "requirements_with_page": sum(1 for req in requirements if req.source_page),
            "requirements_with_score": sum(1 for req in requirements if req.score_value is not None),
            "global_params_filled": filled,
        },
    }


def save_extraction_results(db: Session, project: Project, result: dict) -> list[TechRequirement]:
    """将 LLM 提取结果写入数据库（钛投标五块结构 + 技术评分项）。"""
    global_params = result.get("global_params") or {}

    if global_params.get("name") and not _is_manually_confirmed(project, "name"):
        project.name = global_params["name"]
    if global_params.get("voltage_level") and not _is_manually_confirmed(project, "voltage_level"):
        project.voltage_level = global_params["voltage_level"]
    scale = global_params.get("scale") or global_params.get("capacity")
    if scale and not _is_manually_confirmed(project, "capacity"):
        project.capacity = scale
    if global_params.get("duration_days") is not None and not _is_manually_confirmed(project, "duration_days"):
        try:
            project.duration_days = int(global_params["duration_days"])
        except (TypeError, ValueError):
            pass
    if global_params.get("transformer_count"):
        project.transformer_count = global_params["transformer_count"]
    if global_params.get("location") and not _is_manually_confirmed(project, "location"):
        project.location = global_params["location"]

    meta_fields = {}
    if global_params.get("project_type") and not _is_manually_confirmed(project, "project_type"):
        meta_fields["project_type"] = global_params["project_type"]
    if not _is_manually_confirmed(project, "engineering_domain"):
        from domains.registry import DEFAULT_DOMAIN
        meta_fields["engineering_domain"] = global_params.get("engineering_domain") or DEFAULT_DOMAIN
    if global_params.get("contract_mode") and not _is_manually_confirmed(project, "contract_mode"):
        meta_fields["contract_mode"] = global_params["contract_mode"]
    if global_params.get("extra_notes"):
        meta_fields["extra_notes"] = global_params["extra_notes"]
    if global_params.get("budget_yuan") is not None and not _is_manually_confirmed(project, "budget_yuan"):
        try:
            meta_fields["budget_yuan"] = float(global_params["budget_yuan"])
        except (TypeError, ValueError):
            pass

    contradictions = result.get("contradictions")
    if isinstance(contradictions, list):
        meta_fields["contradictions"] = contradictions

    if meta_fields:
        set_meta(project, **meta_fields)

    db.query(TechRequirement).filter(TechRequirement.project_id == project.id).delete()

    requirements: list[TechRequirement] = []
    seen_titles: list[str] = []
    for item in result.get("requirements") or []:
        title = item.get("requirement_title", "未命名评分项")
        if _is_duplicate_title(title, seen_titles):
            logger.info("跳过重复评分项: %s", title)
            continue
        seen_titles.append(title.strip().lower())
        req = TechRequirement(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requirement_title=title,
            score_value=item.get("score_value"),
            score_category=item.get("score_category"),
            source_text=item.get("source_text"),
            source_page=item.get("source_page"),
            is_risk_item=1 if item.get("is_risk_item") else 0,
            keyword=item.get("keyword"),
            evidence_materials=item.get("evidence_materials"),
            mandatory_elements=item.get("mandatory_elements"),
            risk_hint=item.get("risk_hint"),
            status="pending",
        )
        db.add(req)
        requirements.append(req)

    save_tender_detail_from_extraction(project, result)
    prefill_facts_from_extraction(db, project, result.get("fact_groups"))
    project.status = "confirming"
    db.commit()
    return requirements


def process_upload(db: Session, project: Project, file_path: Path) -> dict:
    """完整解析流程：文档解析 → LLM 提取（钛投标五块 + 技术评分项）→ 入库。"""
    set_parse_error(project, None)
    project.status = "parsing"
    set_parse_progress(project, PARSE_STAGE_READING, "正在阅读文档段落与表格…")
    db.commit()

    parsed = parse_document(file_path)
    if parsed.error:
        set_parse_error(project, parsed.error)
        set_parse_progress(project, PARSE_STAGE_ERROR, parsed.error)
        project.status = "confirming"
        db.commit()
        return {"success": False, "error": parsed.error}

    if not parsed.items:
        err = "未能从文件中提取到有效内容，请检查文件格式。"
        set_parse_error(project, err)
        set_parse_progress(project, PARSE_STAGE_ERROR, err)
        project.status = "confirming"
        db.commit()
        return {"success": False, "error": err}

    para_n = len(parsed.paragraphs)
    table_n = len(parsed.tables)
    set_parse_progress(
        project,
        PARSE_STAGE_EXTRACTING,
        f"已读取 {para_n} 段、{table_n} 个表格，正在提取关键信息…",
        chunk_index=0,
        chunk_total=1,
    )
    db.commit()

    def _on_chunk(chunk_index: int, chunk_total: int, page_hint: str) -> None:
        set_parse_progress(
            project,
            PARSE_STAGE_EXTRACTING,
            f"正在提取关键信息（{page_hint}，{chunk_index}/{chunk_total}）…",
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )
        db.commit()

    try:
        result = extract_with_llm(parsed, on_chunk=_on_chunk)
        set_parse_progress(project, PARSE_STAGE_SAVING, "正在写入评分项与招标详情…")
        db.commit()
        requirements = save_extraction_results(db, project, result)
        blind_detected = apply_blind_bid_detection(project, _parsed_full_text(parsed))
        if blind_detected:
            logger.info("项目 %s 关键词命中暗标，已预勾选 blind_bid=True", project.id)

        def _persist_confidence(info: dict) -> None:
            warnings = list(info.get("warnings") or [])
            if blind_detected and BLIND_BID_DETECT_WARNING not in warnings:
                warnings.insert(0, BLIND_BID_DETECT_WARNING)
            set_meta(
                project,
                parse_confidence=info["confidence"],
                parse_confidence_level=info["level"],
                parse_warnings=warnings,
                parse_stats=info["stats"],
            )

        if not requirements:
            err = (
                "解析完成，但未提取到任何技术评分项。可能原因：文件为商务标/资信标，"
                "或技术评分表格无法识别。请手动确认后继续，或重新上传正确文件。"
            )
            confidence_info = compute_parse_confidence(parsed, result, requirements)
            _persist_confidence(confidence_info)
            set_parse_error(project, err)
            set_parse_progress(project, PARSE_STAGE_DONE, err)
            db.commit()
            return {"success": False, "error": err, "requirement_count": 0, **confidence_info}
        confidence_info = compute_parse_confidence(parsed, result, requirements)
        _persist_confidence(confidence_info)
        set_parse_error(project, None)
        set_parse_progress(
            project,
            PARSE_STAGE_DONE,
            f"解析完成，共提取 {len(requirements)} 条技术评分项",
        )
        db.commit()
        return {
            "success": True,
            "requirement_count": len(requirements),
            "page_count": parsed.page_count,
            "table_count": len(parsed.tables),
            "paragraph_count": len(parsed.paragraphs),
            "blind_bid_auto_detected": blind_detected,
            **confidence_info,
        }
    except Exception as exc:
        logger.exception("LLM 提取失败: %s", exc)
        set_parse_error(project, f"LLM 提取失败: {exc}")
        set_parse_progress(project, PARSE_STAGE_ERROR, f"LLM 提取失败: {exc}")
        project.status = "confirming"
        db.commit()
        return {"success": False, "error": f"LLM 提取失败: {exc}"}

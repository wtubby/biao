"""以标写标：从整份参考文本中按章检索相关片段。"""

from __future__ import annotations

import re

from services.blind_bid_service import _COMPANY_MARKERS, _IDENTITY_PATTERNS

# 单章注入上限（字符），避免盲贴整份参考标书
REFERENCE_BID_CHAPTER_LIMIT = 1800
REFERENCE_BID_TOP_K = 4
_MIN_PARA_LEN = 40


def scrub_reference_identity(text: str) -> str:
    """清洗参考标书中的投标人/公司/联系人等身份信息。

    无论当前项目是否暗标，参考标书注入 prompt 前一律脱敏，
    避免旧标书专有名词被 LLM 抄进新标书。
    """
    if not text:
        return ""
    out = text
    for pattern in _IDENTITY_PATTERNS:
        out = pattern.sub("投标人", out)
    for marker in _COMPANY_MARKERS:
        if marker in out:
            out = out.replace(marker, "投标人")
    # 业绩/业主可追溯表述：合同编号弱化
    out = re.sub(
        r"(?:合同编号|合同号)\s*[:：]?\s*[A-Za-z0-9\-_/]{4,}",
        "合同编号：类似工程",
        out,
    )
    return out


def _tokenize_query(text: str) -> list[str]:
    """优先用检索服务分词；不可用时退化为汉字/词块切分。"""
    try:
        from services.retrieval_core import tokenize
        from services.retrieval_service import expand_tokens

        base = tokenize(text or "")
        return expand_tokens(base) if base else []
    except Exception:
        parts = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{2,}", text or "")
        return list(dict.fromkeys(parts))


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n+", text or "")
    paras: list[str] = []
    for part in parts:
        cleaned = re.sub(r"[ \t]+", " ", part).strip()
        if len(cleaned) < _MIN_PARA_LEN:
            continue
        # 超长段再按句号粗切，便于命中局部
        if len(cleaned) > 800:
            sentences = re.split(r"(?<=[。！？；])", cleaned)
            buf = ""
            for sent in sentences:
                if not sent.strip():
                    continue
                if len(buf) + len(sent) > 500 and buf:
                    paras.append(buf.strip())
                    buf = sent
                else:
                    buf += sent
            if buf.strip():
                paras.append(buf.strip())
        else:
            paras.append(cleaned)
    return paras


def _score_paragraph(para: str, query_tokens: list[str]) -> float:
    if not query_tokens:
        return 0.0
    hits = sum(1 for t in query_tokens if t and t in para)
    length_penalty = min(len(para) / 600.0, 1.5)
    return hits / max(length_penalty, 0.5)


def build_reference_query(
    chapter_title: str,
    guidance: dict | None = None,
    requirement_titles: list[str] | None = None,
) -> str:
    guidance = guidance or {}
    parts = [chapter_title or ""]
    brief = (guidance.get("brief") or "").strip()
    boundary = (guidance.get("content_boundary") or "").strip()
    if brief:
        parts.append(brief[:120])
    if boundary:
        parts.append(boundary[:160])
    if requirement_titles:
        parts.extend(requirement_titles[:5])
    return " ".join(p for p in parts if p)


def select_reference_bid_snippets(
    reference_text: str,
    query: str,
    *,
    top_k: int = REFERENCE_BID_TOP_K,
    max_chars: int = REFERENCE_BID_CHAPTER_LIMIT,
    fallback_to_head: bool = False,
) -> str:
    """按查询从参考标书中选取相关段落。

    默认无命中时不注入（避免文首无关内容污染本章）。
    短文本（整篇不超过 max_chars）视为整篇相关，直接返回。
    返回前一律做身份信息脱敏。
    """
    text = (reference_text or "").strip()
    if not text:
        return ""

    body = ""
    if len(text) <= max_chars:
        body = text
    else:
        paras = _split_paragraphs(text)
        if not paras:
            body = text[:max_chars] if fallback_to_head else ""
        else:
            query_tokens = [t for t in _tokenize_query(query or "") if len(t) >= 2][:40]
            if not query_tokens:
                body = text[:max_chars] if fallback_to_head else ""
            else:
                ranked = sorted(
                    ((_score_paragraph(p, query_tokens), i, p) for i, p in enumerate(paras)),
                    key=lambda x: (-x[0], x[1]),
                )
                positive = [p for score, _i, p in ranked if score > 0]
                if not positive:
                    body = text[:max_chars] if fallback_to_head else ""
                else:
                    selected: list[str] = []
                    total = 0
                    for para in positive[:top_k]:
                        if total + len(para) > max_chars and selected:
                            break
                        selected.append(para)
                        total += len(para)
                        if total >= max_chars:
                            break

                    if not selected:
                        body = text[:max_chars] if fallback_to_head else ""
                    else:
                        body = "\n\n---\n\n".join(selected)
                        if len(body) > max_chars:
                            body = body[:max_chars].rstrip() + "…"

    return scrub_reference_identity(body) if body else ""


def extract_reference_text_from_file(file_path) -> str:
    """从上传的参考标书文件提取纯文本。"""
    from pathlib import Path

    from services.document_parser import parse_document

    path = Path(file_path)
    parsed = parse_document(path)
    if parsed.error:
        raise ValueError(parsed.error)
    parts = [item.text for item in parsed.items if (item.text or "").strip()]
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("未能从参考标书中提取到有效文本")
    # 控制入库体积，避免 generation_config 过大
    max_store = 120_000
    if len(text) > max_store:
        text = text[:max_store].rstrip() + "\n\n…（已截断）"
    return text

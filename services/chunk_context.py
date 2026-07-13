"""知识库 Chunk 上下文前缀（Contextual Retrieval）。"""

from __future__ import annotations

import re
from pathlib import Path

_SENTENCE_END = re.compile(r"[。；;！!？?\n]")


def _topic_snippet(body: str, max_len: int = 36) -> str:
    text = re.sub(r"\s+", " ", (body or "").strip())
    if not text:
        return ""
    m = _SENTENCE_END.search(text)
    if m and m.start() > 8:
        snippet = text[: m.start() + 1].strip()
    else:
        snippet = text[:max_len]
    if len(snippet) > max_len:
        snippet = snippet[: max_len - 1].rstrip() + "…"
    return snippet


def build_chunk_context_prefix(
    *,
    folder: str | None,
    source_file: str,
    keywords: str | None,
    body: str,
    max_chars: int = 80,
) -> str:
    """为切片生成 30~80 字全局背景前缀，供 embed 与 Writer 检索展示。"""
    folder_label = (folder or "知识库").replace("\\", "/").strip("/") or "知识库"
    source_stem = Path(source_file).stem if source_file else "文档"
    kw = (keywords or "").strip()
    kw_part = f"，关键词：{kw}" if kw else ""
    topic = _topic_snippet(body)
    if topic:
        prefix = f"【所属：{folder_label}/{source_stem}{kw_part}】{topic}"
    else:
        prefix = f"【所属：{folder_label}/{source_stem}{kw_part}】"
    if len(prefix) > max_chars:
        return prefix[: max_chars - 1].rstrip() + "…"
    return prefix


def chunk_embed_text(body: str, context_prefix: str | None) -> str:
    """Embedding 输入：前缀 + 正文。"""
    body = (body or "").strip()
    prefix = (context_prefix or "").strip()
    if prefix:
        return f"{prefix}\n{body}" if body else prefix
    return body


def chunk_display_text(body: str, context_prefix: str | None) -> str:
    """返回给 Writer/QA 的展示文本。"""
    return chunk_embed_text(body, context_prefix)

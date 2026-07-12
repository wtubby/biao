"""将 knowledge_source/ 下的原始素材（历史标书片段/工艺文档纯文本）
用 LLM 辅助切分为带关键词标签的知识条目，写入 knowledge/<folder>/。

用法：python scripts/import_knowledge.py knowledge_source/土建/xxx.txt --folder 土建工程
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import KNOWLEDGE_ROOT  # noqa: E402
from llm.llm_client import call_llm_json  # noqa: E402
from services.embedding_service import text_hash  # noqa: E402

_SYSTEM_PROMPT = """你是标书知识库整理助手。将输入的施工工艺/技术方案原始文本，
切分为若干条独立的知识片段，每条 300-800 字，聚焦单一工艺点或单一技术要点。
要求：
1. 去除任何具体项目名称、公司名称、中标信息等敏感/特定信息，只保留通用工艺描述
2. 每条提取 2-5 个关键词（覆盖该条涉及的设备/工艺/动作）
3. 每条标注适用的技术标章节类型（如：GIS组合电器安装方案、质量保证措施）
4. 只输出 JSON，不要额外解释

输出格式：
{"items": [{"keywords": ["关键词1","关键词2"], "scope": ["适用章节1"], "content": "正文..."}]}"""


def _format_chunk(item: dict) -> str:
    kw = ", ".join(item.get("keywords", []))
    scope = ", ".join(item.get("scope", []))
    lines = []
    if kw:
        lines.append(f"## 关键词: {kw}")
    if scope:
        lines.append(f"## 适用章节: {scope}")
    lines.append("")
    lines.append(item.get("content", "").strip())
    return "\n".join(lines)


def import_file(src_path: Path, folder: str, dry_run: bool = False) -> int:
    raw = src_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw:
        return 0

    result = call_llm_json(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": raw[:6000]},  # 超长原文分批调用，此处简化
        ]
    )
    items = result.get("items", [])
    if not items:
        print(f"[跳过] {src_path} 未提取到条目")
        return 0

    out_dir = Path(KNOWLEDGE_ROOT) / folder
    out_dir.mkdir(parents=True, exist_ok=True)

    # 去重：against 已存在文件里的正文 hash
    existing_hashes = set()
    for p in out_dir.glob("*.txt"):
        for para in re.split(r"\n\s*\n", p.read_text(encoding="utf-8", errors="ignore")):
            body = para.strip()
            if body:
                existing_hashes.add(text_hash(body))

    written = 0
    out_lines = []
    for item in items:
        body = (item.get("content") or "").strip()
        if len(body) < 20 or text_hash(body) in existing_hashes:
            continue
        out_lines.append(_format_chunk(item))
        written += 1

    if not out_lines:
        print(f"[跳过] {src_path} 全部重复")
        return 0

    if dry_run:
        print(f"[预览] {src_path} -> {written} 条\n" + "\n\n".join(out_lines[:2]))
        return written

    out_file = out_dir / f"import_{src_path.stem}.txt"
    out_file.write_text("\n\n".join(out_lines), encoding="utf-8")
    print(f"[写入] {out_file} ({written} 条)")
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--folder", required=True, help="目标 knowledge/ 子目录名")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    import_file(args.source, args.folder, args.dry_run)

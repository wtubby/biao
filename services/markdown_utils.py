"""Markdown 解析工具（assembler / qa 共用）。"""

from __future__ import annotations

import re


def parse_table_cells(row: str) -> list[str]:
    """把一行 Markdown 表格行拆成单元格文本，去掉首尾竖线，处理转义竖线 \\|。"""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    cells = re.split(r"(?<!\\)\|", row)
    return [c.strip().replace("\\|", "|") for c in cells]

"""轻量 SQLite schema 补丁（无 Alembic 时用于加列）。"""

from __future__ import annotations

import logging

from sqlalchemy import text

from db.database import engine

logger = logging.getLogger(__name__)

BID_SCOPE_TECHNICAL = "technical"
BID_SCOPE_TECHNICAL_COMMERCIAL = "technical_commercial"


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def ensure_schema() -> None:
    """create_all 之后调用：为已有表补列。"""
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "projects" in tables:
            cols = _table_columns(conn, "projects")
            if "bid_scope" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE projects ADD COLUMN bid_scope TEXT "
                        f"DEFAULT '{BID_SCOPE_TECHNICAL}'"
                    )
                )
                logger.info("已为 projects 表添加 bid_scope 列")
            # 回填空值
            conn.execute(
                text(
                    "UPDATE projects SET bid_scope = :scope "
                    "WHERE bid_scope IS NULL OR bid_scope = ''"
                ),
                {"scope": BID_SCOPE_TECHNICAL},
            )

        if "knowledge_chunks" in tables:
            kc_cols = _table_columns(conn, "knowledge_chunks")
            if "keywords" not in kc_cols:
                conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN keywords TEXT"))
                logger.info("已为 knowledge_chunks 表添加 keywords 列")

            # 先清历史重复，再补 (folder_path, chunk_hash) 唯一索引
            indexes = {
                row[1]
                for row in conn.execute(
                    text("PRAGMA index_list(knowledge_chunks)")
                ).fetchall()
            }
            if "uq_knowledge_chunks_folder_hash" not in indexes:
                conn.execute(
                    text(
                        "DELETE FROM knowledge_chunks WHERE id NOT IN ("
                        "  SELECT MIN(id) FROM knowledge_chunks"
                        "  GROUP BY folder_path, chunk_hash"
                        ")"
                    )
                )
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX uq_knowledge_chunks_folder_hash "
                        "ON knowledge_chunks(folder_path, chunk_hash)"
                    )
                )
                logger.info("已为 knowledge_chunks 添加 (folder_path, chunk_hash) 唯一索引")

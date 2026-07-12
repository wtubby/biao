import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    voltage_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    capacity: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transformer_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    bid_scope: Mapped[str] = mapped_column(Text, default="technical")
    status: Mapped[str] = mapped_column(Text, default="draft")
    pause_requested: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TechRequirement(Base):
    __tablename__ = "tech_requirements"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    requirement_title: Mapped[str] = mapped_column(Text)
    score_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_risk_item: Mapped[int] = mapped_column(Integer, default=0)
    keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_materials: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory_elements: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")


class TechOutline(Base):
    __tablename__ = "tech_outline"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    is_leaf: Mapped[int] = mapped_column(Integer, default=0)
    bound_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirement_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    writing_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_locked: Mapped[int] = mapped_column(Integer, default=0)
    review_status: Mapped[str] = mapped_column(Text, default="init")
    review_errors: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_debug: Mapped[str | None] = mapped_column(Text, nullable=True)


class GlobalFact(Base):
    __tablename__ = "global_facts"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    folder_path: Mapped[str] = mapped_column(Text)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    resume: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    folder_path: Mapped[str] = mapped_column(Text, index=True)
    source_file: Mapped[str] = mapped_column(Text)
    chunk_hash: Mapped[str] = mapped_column(Text, index=True)
    text: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)  # 逗号/顿号分隔
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class KnowledgeFolderStatus(Base):
    __tablename__ = "knowledge_folder_status"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    folder_path: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ChapterVersion(Base):
    __tablename__ = "chapter_versions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    chapter_id: Mapped[str] = mapped_column(Text, index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="manual")
    review_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CommercialSection(Base):
    """商务/资格响应章节（模板轨道，不走技术标 LLM 逐章流程）。"""

    __tablename__ = "commercial_sections"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    section_key: Mapped[str] = mapped_column(Text)  # notice|commerce_requirement|qualification|commerce_score
    match_key: Mapped[str] = mapped_column(Text, default="")  # 稳定匹配键，regenerate 时保留 confirmed
    title: Mapped[str] = mapped_column(Text)
    content_markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="draft")  # draft | confirmed
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

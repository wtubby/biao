"""一次性脚本：拆分 writer_service 为子模块。"""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "services"
src_lines = (root / "writer_service.py").read_text(encoding="utf-8").splitlines(keepends=True)

context_start = 99
gen_start = 420
qa_start = 702
orch_start = 1005

context_body = "".join(src_lines[context_start:gen_start])
gen_body = "".join(src_lines[gen_start:qa_start])
qa_body = "".join(src_lines[qa_start:orch_start])

context_header = '''"""章节上下文 bundle 组装。"""

import json
import logging

from sqlalchemy.orm import Session

from config import WRITER_GUIDE_USER_MAX_CHARS, WRITER_SYSTEM_COMPACT
from db.models import GlobalFact, Project, TechOutline, TechRequirement
from domains.registry import DEFAULT_DOMAIN
from prompts.writer_prompt import (
    build_key_chapter_init_prompt,
    compact_writing_guide,
    get_writer_system_prompt,
)
from services.blind_bid_service import blind_bid_writer_constraints, is_blind_bid
from services.generation_config import (
    chart_density_hint,
    get_generation_config,
    standards_pack_hint,
)
from services.project_meta import get_meta
from services.prompt_project_info import build_prompt_global_params
from services.reference_bid_service import build_reference_query, select_reference_bid_snippets
from services.requirement_prompt import (
    build_chapter_evaluation_focus,
    format_requirements_text,
    maybe_refine_evaluation_focus,
    requirements_response_hint,
)
from services.response_matrix_service import format_chapter_matrix_context
from services.retrieval_service import RetrievalResult, build_retrieval_warning, retrieve_detailed
from services.writing_guidance import (
    default_content_boundary_for_title,
    parse_writing_guidance,
)

logger = logging.getLogger(__name__)

_KEY_CHAPTER_KEYWORDS = ("施工方案", "技术方案", "施工组织", "总体方案", "专项方案")


'''

gen_header = '''"""章节内容规划与 LLM 生成。"""

import logging

from config import (
    KEY_CHAPTER_MIN_SCORE,
    LONG_CHAPTER_MIN_KEY_POINTS,
    LONG_CHAPTER_WORD_THRESHOLD,
    SKIP_CONTENT_PLAN_WORD_THRESHOLD,
)
from domains.registry import DEFAULT_DOMAIN
from llm.llm_client import call_llm_json, call_llm_text
from prompts.plan_prompt import build_plan_user_prompt, get_plan_system_prompt
from prompts.writer_prompt import (
    SUMMARY_SYSTEM_PROMPT,
    build_writer_user_prompt,
    get_writer_system_prompt,
    sample_content_for_summary,
)
from services.qa_rules import (
    check_segment_stitch_quality,
    fallback_content_plan,
    validate_content_plan,
)
from services.retrieval_service import retrieve_detailed
from services.writing_guidance import should_skip_content_plan

logger = logging.getLogger(__name__)


'''

qa_header = '''"""章节硬/软质检编排。"""

import logging
import re

from config import (
    MIN_DIGIT_RATIO,
    WORD_COUNT_MAX_RATIO,
    WORD_COUNT_MIN_RATIO,
)
from db.models import Project, TechOutline, TechRequirement
from llm.llm_client import call_llm_json
from prompts.qa_prompt import (
    QA_SYSTEM_PROMPT,
    build_qa_user_prompt,
    sample_content_windows_for_qa,
)
from services.blind_bid_service import is_blind_bid
from services.chapter_generation_service import generate_summary
from services.chapter_review_errors import dump_review_errors, merge_review_errors
from services.project_meta import get_meta
from services.qa_rules import (
    check_ai_cliche_residues,
    check_ai_spacing,
    check_blind_bid_residues,
    check_chart_renderability,
    check_chapter_scope,
    check_cross_chapter_overlap,
    check_descriptive_chapter_measures,
    check_fabricated_standards,
    check_first_paragraph_repeats_title,
    check_global_fact_consistency,
    check_heading_keyword_coverage,
    check_markdown_table_integrity,
    check_paragraph_opening_repetition,
    check_plan_key_points_coverage,
    check_scoring_coverage_in_content,
    check_stitch_cheat,
    check_template_residues,
    check_truncation_risk,
    split_keywords,
    trim_out_of_scope_content,
)
from services.response_matrix_service import matrix_issues_for_chapter
from services.writing_guidance import is_descriptive_chapter

logger = logging.getLogger(__name__)


'''

(root / "chapter_context_service.py").write_text(context_header + context_body, encoding="utf-8")
(root / "chapter_generation_service.py").write_text(gen_header + gen_body, encoding="utf-8")
(root / "chapter_qa_orchestrator.py").write_text(qa_header + qa_body, encoding="utf-8")
print("done")

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH, override=True)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
# Maker-Checker：留空则回退为 DEEPSEEK_MODEL
WRITER_MODEL = os.getenv("WRITER_MODEL", "").strip()
QA_MODEL = os.getenv("QA_MODEL", "").strip()
# 对带 schema 的 JSON 调用尝试 json_schema strict；不支持时自动降级 json_object
LLM_USE_JSON_SCHEMA = os.getenv("LLM_USE_JSON_SCHEMA", "1").lower() in ("1", "true", "yes")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_MAX_TOKENS_CEILING = int(os.getenv("LLM_MAX_TOKENS_CEILING", "8000"))
CHARS_PER_TOKEN_CN = float(os.getenv("CHARS_PER_TOKEN_CN", "0.6"))
LLM_TEXT_MAX_CONTINUATIONS = int(os.getenv("LLM_TEXT_MAX_CONTINUATIONS", "2"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_NETWORK_MAX_RETRIES = int(os.getenv("LLM_NETWORK_MAX_RETRIES", "3"))
LLM_NETWORK_RETRY_BASE_DELAY = float(os.getenv("LLM_NETWORK_RETRY_BASE_DELAY", "1.0"))

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "tbe.db"))
KNOWLEDGE_ROOT = os.getenv("KNOWLEDGE_ROOT", str(BASE_DIR / "knowledge"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(BASE_DIR / "output"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))

API_PORT = int(os.getenv("API_PORT", "3333"))


def get_cors_origins() -> list[str]:
    """CORS 允许来源。未配置时默认仅本机 API 端口（与 start.bat / .env 中 API_PORT 一致）。"""
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        f"http://localhost:{API_PORT}",
        f"http://127.0.0.1:{API_PORT}",
    ]


BM25_TOP_K = int(os.getenv("BM25_TOP_K", "5"))
# 自适应 RAG：按章节类型动态 top_k / 是否走向量
ENABLE_ADAPTIVE_RAG = os.getenv("ENABLE_ADAPTIVE_RAG", "1").lower() in ("1", "true", "yes")
RETRIEVAL_TOP_K_LIGHT = int(os.getenv("RETRIEVAL_TOP_K_LIGHT", "3"))
RETRIEVAL_TOP_K_DEEP = int(os.getenv("RETRIEVAL_TOP_K_DEEP", "8"))
RETRIEVAL_TOP_K_PLAN_FOLLOWUP = int(os.getenv("RETRIEVAL_TOP_K_PLAN_FOLLOWUP", "4"))
EMBEDDING_MODEL_PATH = os.getenv(
    "EMBEDDING_MODEL_PATH",
    str(BASE_DIR / "models" / "bge-small-zh-v1.5"),
)
EMBEDDING_ENABLED = os.getenv("EMBEDDING_ENABLED", "1").lower() in ("1", "true", "yes")
RETRIEVAL_RRF_K = int(os.getenv("RETRIEVAL_RRF_K", "60"))
MIN_DIGIT_RATIO = float(os.getenv("MIN_DIGIT_RATIO", "0.5"))
MAX_QA_RETRY = int(os.getenv("MAX_QA_RETRY", "2"))
TARGET_PAGES_DEFAULT = int(os.getenv("TARGET_PAGES_DEFAULT", "40"))
WORDS_PER_SCORE_PAGE = int(os.getenv("WORDS_PER_SCORE_PAGE", "780"))
WORD_COUNT_MIN_RATIO = float(os.getenv("WORD_COUNT_MIN_RATIO", "0.75"))
WORD_COUNT_MAX_RATIO = float(os.getenv("WORD_COUNT_MAX_RATIO", "1.25"))
# 目标字数达到该阈值时，按写作规划要点分段生成再拼接
LONG_CHAPTER_WORD_THRESHOLD = int(os.getenv("LONG_CHAPTER_WORD_THRESHOLD", "1800"))
LONG_CHAPTER_MIN_KEY_POINTS = int(os.getenv("LONG_CHAPTER_MIN_KEY_POINTS", "4"))
# 规划期结构拆分：叶子目标字数达到阈值时可拆为 3~4 个子节点
LONG_LEAF_SPLIT_THRESHOLD = int(os.getenv("LONG_LEAF_SPLIT_THRESHOLD", "1500"))
LONG_LEAF_SPLIT_TARGET_PER_CHILD = int(os.getenv("LONG_LEAF_SPLIT_TARGET_PER_CHILD", "800"))
LONG_LEAF_SPLIT_MIN_CHILDREN = int(os.getenv("LONG_LEAF_SPLIT_MIN_CHILDREN", "3"))
LONG_LEAF_SPLIT_MAX_CHILDREN = int(os.getenv("LONG_LEAF_SPLIT_MAX_CHILDREN", "4"))
LONG_LEAF_MAX_LEVEL = int(os.getenv("LONG_LEAF_MAX_LEVEL", "4"))
# 同级接力：注入 Writer Prompt 的上一同级正文上限（字符）
IMMEDIATE_PRIOR_SIBLING_MAX_CHARS = int(os.getenv("IMMEDIATE_PRIOR_SIBLING_MAX_CHARS", "1500"))
GENERATION_CONCURRENCY = int(os.getenv("GENERATION_CONCURRENCY", "3"))
GENERATION_PARALLEL_SECTIONS = os.getenv("GENERATION_PARALLEL_SECTIONS", "0").lower() in ("1", "true", "yes")
PIPELINE_STAGE_MAX_RETRIES = int(os.getenv("PIPELINE_STAGE_MAX_RETRIES", "2"))
PIPELINE_STAGE_TIMEOUT_SECONDS = int(os.getenv("PIPELINE_STAGE_TIMEOUT_SECONDS", "600"))
KEY_CHAPTER_MIN_SCORE = float(os.getenv("KEY_CHAPTER_MIN_SCORE", "5.0"))
ENABLE_CONTENT_PLAN = os.getenv("ENABLE_CONTENT_PLAN", "1").lower() in ("1", "true", "yes")
# 目标字数低于该阈值时跳过 LLM 写作规划，改用规则兜底
SKIP_CONTENT_PLAN_WORD_THRESHOLD = int(os.getenv("SKIP_CONTENT_PLAN_WORD_THRESHOLD", "500"))
# 压缩 writer system：完整领域指南改注入 user prompt 摘要
WRITER_SYSTEM_COMPACT = os.getenv("WRITER_SYSTEM_COMPACT", "1").lower() in ("1", "true", "yes")
WRITER_GUIDE_USER_MAX_CHARS = int(os.getenv("WRITER_GUIDE_USER_MAX_CHARS", "600"))
# Writer 结构化输出：正文与 embedded_charts 分字段，消除图表占位符格式错误
WRITER_STRUCTURED_OUTPUT = os.getenv("WRITER_STRUCTURED_OUTPUT", "1").lower() in ("1", "true", "yes")
# 长章分段撰写时，每段生成后做轻量 QA 闭环（不过则重写该段）
ENABLE_SEGMENT_QA = os.getenv("ENABLE_SEGMENT_QA", "1").lower() in ("1", "true", "yes")
MAX_SEGMENT_QA_RETRY = int(os.getenv("MAX_SEGMENT_QA_RETRY", "1"))
# 知识库 Chunk 上下文前缀（Contextual Retrieval）
ENABLE_CHUNK_CONTEXT_PREFIX = os.getenv("ENABLE_CHUNK_CONTEXT_PREFIX", "1").lower() in ("1", "true", "yes")
# 记录 LLM 响应中的 prompt_cache_hit_tokens（DeepSeek 等自动前缀缓存）
LOG_PROMPT_CACHE_USAGE = os.getenv("LOG_PROMPT_CACHE_USAGE", "1").lower() in ("1", "true", "yes")
# 高分施工章用 LLM 精炼评标关注点（默认关闭，避免额外延迟）
EVALUATION_FOCUS_LLM_REFINE = os.getenv("EVALUATION_FOCUS_LLM_REFINE", "0").lower() in ("1", "true", "yes")
EVALUATION_FOCUS_REFINE_MIN_SCORE = float(os.getenv("EVALUATION_FOCUS_REFINE_MIN_SCORE", "8"))
WRITING_GUIDE_PATH = os.getenv(
    "WRITING_GUIDE_PATH",
    str(BASE_DIR / "templates" / "电力EPC技术标写作指南.md"),
)
# 章节标题多级编号：none | decimal | chapter_cn | outline_mixed
HEADING_NUMBERING_PRESET = os.getenv("HEADING_NUMBERING_PRESET", "decimal")


def reload_settings():
    """从 .env 重新加载 LLM 相关配置（前端保存设置后调用）。"""
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    global WRITER_MODEL, QA_MODEL, LLM_USE_JSON_SCHEMA
    global LLM_MAX_TOKENS, LLM_MAX_TOKENS_CEILING, CHARS_PER_TOKEN_CN
    global LLM_TEXT_MAX_CONTINUATIONS, LLM_TEMPERATURE

    load_dotenv(ENV_PATH, override=True)
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    WRITER_MODEL = os.getenv("WRITER_MODEL", "").strip()
    QA_MODEL = os.getenv("QA_MODEL", "").strip()
    LLM_USE_JSON_SCHEMA = os.getenv("LLM_USE_JSON_SCHEMA", "1").lower() in ("1", "true", "yes")
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    LLM_MAX_TOKENS_CEILING = int(os.getenv("LLM_MAX_TOKENS_CEILING", "8000"))
    CHARS_PER_TOKEN_CN = float(os.getenv("CHARS_PER_TOKEN_CN", "0.6"))
    LLM_TEXT_MAX_CONTINUATIONS = int(os.getenv("LLM_TEXT_MAX_CONTINUATIONS", "2"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))


# 确保运行时目录存在
for _dir in (OUTPUT_DIR, UPLOAD_DIR, KNOWLEDGE_ROOT):
    Path(_dir).mkdir(parents=True, exist_ok=True)

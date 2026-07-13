import json
import logging
import random
import re
import time
from typing import Any, Literal

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

LLMRole = Literal["default", "writer", "qa"]

_RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, RateLimitError)

_client: OpenAI | None = None
_cache_stats: dict[str, int] = {
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 0,
    "requests": 0,
}


def reset_client():
    """设置变更后重置 LLM 客户端。"""
    global _client
    _client = None


def get_client() -> OpenAI:
    global _client
    import config as cfg

    if _client is None:
        _client = OpenAI(api_key=cfg.DEEPSEEK_API_KEY, base_url=cfg.DEEPSEEK_BASE_URL)
    return _client


def resolve_model(*, role: LLMRole = "default", model: str | None = None) -> str:
    """按角色解析模型：writer/qa 可配置异构模型，留空则回退 DEEPSEEK_MODEL。"""
    import config as cfg

    if model and str(model).strip():
        return str(model).strip()
    if role == "writer" and cfg.WRITER_MODEL:
        return cfg.WRITER_MODEL
    if role == "qa" and cfg.QA_MODEL:
        return cfg.QA_MODEL
    return cfg.DEEPSEEK_MODEL


def _is_retryable_status_error(exc: APIStatusError) -> bool:
    """5xx 服务端错误值得重试；4xx（密钥错、参数错、内容审核拒绝等）不重试。"""
    return exc.status_code is not None and exc.status_code >= 500


def get_cache_usage_stats() -> dict[str, int]:
    """累计 prompt 缓存命中统计（进程内）。"""
    return dict(_cache_stats)


def reset_cache_usage_stats() -> None:
    global _cache_stats
    _cache_stats = {
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "requests": 0,
    }


def _record_cache_usage(response: Any) -> None:
    import config as cfg

    if not cfg.LOG_PROMPT_CACHE_USAGE:
        return
    usage = getattr(response, "usage", None)
    if not usage:
        return
    hit = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
    miss = int(getattr(usage, "prompt_cache_miss_tokens", 0) or 0)
    if hit == 0 and miss == 0:
        return
    _cache_stats["prompt_cache_hit_tokens"] += hit
    _cache_stats["prompt_cache_miss_tokens"] += miss
    _cache_stats["requests"] += 1
    if hit > 0:
        logger.info(
            "LLM 前缀缓存命中 %d tokens，未命中 %d tokens（累计命中 %d）",
            hit,
            miss,
            _cache_stats["prompt_cache_hit_tokens"],
        )


def _create_completion_with_retry(client: OpenAI, **create_kwargs) -> Any:
    """对 client.chat.completions.create 做网络层重试：限流/超时/连接失败/5xx，指数退避+抖动。"""
    import config as cfg

    max_retries = cfg.LLM_NETWORK_MAX_RETRIES
    base_delay = cfg.LLM_NETWORK_RETRY_BASE_DELAY
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(**create_kwargs)
            _record_cache_usage(response)
            return response
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
        except APIStatusError as exc:
            if not _is_retryable_status_error(exc):
                raise
            last_exc = exc

        if attempt >= max_retries:
            break
        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
        logger.warning(
            "LLM 请求出现瞬时错误（%s: %s），%.1fs 后重试（%d/%d）",
            type(last_exc).__name__, last_exc, delay, attempt + 1, max_retries,
        )
        time.sleep(delay)

    logger.error("LLM 请求经 %d 次重试后仍失败: %s", max_retries, last_exc)
    raise last_exc


def _strip_markdown_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _repair_json_text(text: str) -> str:
    """修复 LLM 常见 JSON 格式问题（尾逗号等）。"""
    text = text.strip()
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def _recover_truncated_nodes_json(text: str) -> dict[str, Any] | None:
    """尝试从因 token 截断的不完整 JSON 中恢复 nodes 数组。"""
    if '"nodes"' not in text:
        return None

    match = re.search(r'\{\s*"nodes"\s*:\s*\[', text)
    if not match:
        return None

    prefix = text[: match.end()]
    body = text[match.end() :]
    ends = [m.start() + 1 for m in re.finditer(r"\}\s*,", body)]
    for end in reversed(ends):
        candidate = prefix + body[:end] + "]}"
        try:
            data = json.loads(candidate)
            nodes = data.get("nodes")
            if isinstance(nodes, list) and nodes:
                return data
        except json.JSONDecodeError:
            continue
    return None


def _recover_truncated_array_json(text: str, key: str) -> dict[str, Any] | None:
    """尝试从截断 JSON 中恢复指定数组字段（如 requirements）。"""
    array_match = re.search(rf'"{re.escape(key)}"\s*:\s*\[', text)
    if not array_match:
        return None
    start_brace = text.find("{")
    if start_brace < 0:
        return None

    prefix = text[start_brace:array_match.end()]
    body = text[array_match.end():]
    ends = [m.start() + 1 for m in re.finditer(r"\}\s*,", body)]
    for end in reversed(ends):
        candidate = prefix + body[:end] + "]}"
        try:
            data = json.loads(candidate)
            arr = data.get(key)
            if isinstance(arr, list) and arr:
                return data
        except json.JSONDecodeError:
            continue
    return None


def _recover_truncated_json(text: str) -> dict[str, Any] | None:
    """尝试从因 token 截断的不完整 JSON 中恢复。"""
    for key in ("nodes", "requirements"):
        if f'"{key}"' not in text:
            continue
        if key == "nodes":
            recovered = _recover_truncated_nodes_json(text)
        else:
            recovered = _recover_truncated_array_json(text, key)
        if recovered is not None:
            return recovered
    return None


def _parse_llm_json(text: str) -> dict[str, Any]:
    cleaned = _repair_json_text(_strip_markdown_json(text))
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        recovered = _recover_truncated_json(cleaned)
        if recovered is not None:
            return recovered
        raise


def _build_response_format(schema: type[BaseModel] | None) -> dict[str, Any]:
    if schema is None:
        return {"type": "json_object"}
    import config as cfg

    if not cfg.LLM_USE_JSON_SCHEMA:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "strict": True,
            "schema": schema.model_json_schema(),
        },
    }


def _validate_with_schema(data: dict[str, Any], schema: type[BaseModel]) -> dict[str, Any]:
    return schema.model_validate(data).model_dump()


def _schema_validation_hint(exc: ValidationError) -> str:
    return (
        "你上次返回的 JSON 结构不符合要求："
        + "; ".join(err["msg"] for err in exc.errors()[:5])
        + "。请严格按约定字段重新输出完整 JSON。"
    )


def call_llm_json(
    messages: list[dict[str, str]],
    max_retries: int = 2,
    timeout: float = 120.0,
    max_tokens: int | None = None,
    truncation_hint: str | None = None,
    *,
    model: str | None = None,
    role: LLMRole = "default",
    schema: type[BaseModel] | None = None,
) -> dict[str, Any]:
    """调用 LLM 并解析 JSON 响应，内置重试机制；可选 Pydantic Schema 强校验。"""
    import config as cfg

    client = get_client()
    current_messages = list(messages)
    token_limit = max_tokens or cfg.LLM_MAX_TOKENS
    resolved_model = resolve_model(role=role, model=model)
    use_json_schema = bool(schema and cfg.LLM_USE_JSON_SCHEMA)
    response_format = _build_response_format(schema)

    for attempt in range(max_retries + 1):
        try:
            response = _create_completion_with_retry(
                client,
                model=resolved_model,
                messages=current_messages,
                response_format=response_format,
                max_tokens=token_limit,
                temperature=cfg.LLM_TEMPERATURE,
                timeout=timeout,
            )
        except APIStatusError as exc:
            if (
                use_json_schema
                and schema is not None
                and exc.status_code == 400
                and response_format.get("type") == "json_schema"
            ):
                logger.warning("json_schema 不受支持，降级为 json_object: %s", exc)
                response_format = {"type": "json_object"}
                use_json_schema = False
                response = _create_completion_with_retry(
                    client,
                    model=resolved_model,
                    messages=current_messages,
                    response_format=response_format,
                    max_tokens=token_limit,
                    temperature=cfg.LLM_TEMPERATURE,
                    timeout=timeout,
                )
            else:
                raise

        choice = response.choices[0]
        raw = choice.message.content or ""
        truncated = choice.finish_reason == "length"

        try:
            data = _parse_llm_json(raw)
            if schema is not None:
                return _validate_with_schema(data, schema)
            return data
        except json.JSONDecodeError as exc:
            if attempt >= max_retries:
                hint = "（响应可能被截断，请减少章节数量或调大 LLM_MAX_TOKENS）" if truncated else ""
                raise ValueError(
                    f"LLM 返回非法 JSON（已重试 {max_retries} 次）{hint}: {exc}"
                ) from exc
            current_messages.append({"role": "assistant", "content": raw})
            retry_hint = (
                truncation_hint
                or "你上次返回的 JSON 因输出过长被截断，请重新输出完整 JSON，不要省略任何数组元素。"
                if truncated
                else (
                    f"你上次返回的内容不是合法 JSON（{exc}）。"
                    "请仅输出一个合法的 JSON 对象，"
                    "不要包含 Markdown 代码块、尾逗号或其他说明文字。"
                )
            )
            current_messages.append({"role": "user", "content": retry_hint})
        except ValidationError as exc:
            if attempt >= max_retries:
                raise ValueError(
                    f"LLM 返回 JSON 未通过 Schema 校验（已重试 {max_retries} 次）: {exc}"
                ) from exc
            current_messages.append({"role": "assistant", "content": raw})
            current_messages.append({"role": "user", "content": _schema_validation_hint(exc)})

    raise ValueError("LLM JSON 调用失败")


def call_llm_text(
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
    timeout: float = 120.0,
    max_continuations: int | None = None,
    *,
    model: str | None = None,
    role: LLMRole = "default",
) -> str:
    """调用 LLM 返回纯文本，若响应被截断（finish_reason == 'length'）自动续写拼接。"""
    import config as cfg

    client = get_client()
    token_limit = max_tokens or cfg.LLM_MAX_TOKENS
    resolved_model = resolve_model(role=role, model=model)
    continuations_left = (
        cfg.LLM_TEXT_MAX_CONTINUATIONS if max_continuations is None else max_continuations
    )

    current_messages = list(messages)
    full_text = ""

    for attempt in range(continuations_left + 1):
        response = _create_completion_with_retry(
            client,
            model=resolved_model,
            messages=current_messages,
            max_tokens=token_limit,
            temperature=cfg.LLM_TEMPERATURE,
            timeout=timeout,
        )
        choice = response.choices[0]
        piece = choice.message.content or ""
        full_text += piece

        if choice.finish_reason != "length":
            return full_text

        if attempt >= continuations_left:
            logger.warning(
                "文本生成达到最大续写次数（%d）仍被截断，返回当前已生成内容（约 %d 字）",
                continuations_left,
                len(full_text),
            )
            return full_text

        logger.info("检测到输出被截断（finish_reason=length），第 %d 次自动续写", attempt + 1)
        current_messages = current_messages + [
            {"role": "assistant", "content": piece},
            {
                "role": "user",
                "content": (
                    "你上一条回复因长度限制被截断了。请紧接着上次中断的地方继续写，"
                    "不要重复已经写过的内容，不要重新输出标题或开场白，直接接着写正文。"
                ),
            },
        ]

    return full_text

from pathlib import Path

from dotenv import dotenv_values, set_key

from config import BASE_DIR

ENV_PATH = BASE_DIR / ".env"
EXAMPLE_PATH = BASE_DIR / ".env.example"

DEFAULTS = {
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-chat",
    "LLM_MAX_TOKENS": "4096",
    "LLM_TEMPERATURE": "0.3",
}


def _ensure_env_file():
    if not ENV_PATH.exists():
        if EXAMPLE_PATH.exists():
            ENV_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            ENV_PATH.write_text("", encoding="utf-8")


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def _is_masked_key(value: str) -> bool:
    return "****" in value


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def get_settings() -> dict:
    _ensure_env_file()
    values = {**DEFAULTS, **dotenv_values(ENV_PATH)}
    api_key = values.get("DEEPSEEK_API_KEY") or ""

    return {
        "api_key_masked": _mask_key(api_key),
        "api_key_configured": bool(api_key and not api_key.startswith("sk-xxxxxxxx")),
        "base_url": values.get("DEEPSEEK_BASE_URL") or DEFAULTS["DEEPSEEK_BASE_URL"],
        "model": values.get("DEEPSEEK_MODEL") or DEFAULTS["DEEPSEEK_MODEL"],
        "max_tokens": _safe_int(values.get("LLM_MAX_TOKENS"), int(DEFAULTS["LLM_MAX_TOKENS"])),
        "temperature": _safe_float(values.get("LLM_TEMPERATURE"), float(DEFAULTS["LLM_TEMPERATURE"])),
    }


def update_settings(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict:
    _ensure_env_file()

    if api_key is not None and api_key.strip() and not _is_masked_key(api_key):
        set_key(str(ENV_PATH), "DEEPSEEK_API_KEY", api_key.strip())

    if base_url is not None:
        set_key(str(ENV_PATH), "DEEPSEEK_BASE_URL", base_url.strip())

    if model is not None:
        set_key(str(ENV_PATH), "DEEPSEEK_MODEL", model.strip())

    if max_tokens is not None:
        set_key(str(ENV_PATH), "LLM_MAX_TOKENS", str(max_tokens))

    if temperature is not None:
        set_key(str(ENV_PATH), "LLM_TEMPERATURE", str(temperature))

    from config import reload_settings
    from llm.llm_client import reset_client

    reload_settings()
    reset_client()

    return get_settings()

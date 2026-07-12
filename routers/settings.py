from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from domains.registry import list_domain_keys
from services.settings_service import get_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsOut(BaseModel):
    api_key_masked: str
    api_key_configured: bool
    base_url: str
    model: str
    max_tokens: int
    temperature: float


class SettingsUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    max_tokens: int | None = Field(None, ge=256, le=32000)
    temperature: float | None = Field(None, ge=0, le=2)


class TestResult(BaseModel):
    success: bool
    message: str


@router.get("/domains")
def read_domains():
    """工程领域注册表，供前端下拉选择。"""
    return {"domains": list_domain_keys()}


@router.get("", response_model=SettingsOut)
def read_settings():
    return get_settings()


@router.put("", response_model=SettingsOut)
def save_settings(body: SettingsUpdate):
    return update_settings(
        api_key=body.api_key,
        base_url=body.base_url,
        model=body.model,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )


@router.post("/test", response_model=TestResult)
def test_api_connection():
    import config as cfg
    from llm.llm_client import get_client

    if not cfg.DEEPSEEK_API_KEY or cfg.DEEPSEEK_API_KEY.startswith("sk-xxxxxxxx"):
        raise HTTPException(status_code=400, detail="请先配置有效的 API Key")

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=cfg.DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": "回复 OK"}],
            max_tokens=10,
            temperature=0,
            timeout=30,
        )
        content = (response.choices[0].message.content or "").strip()
        return {"success": True, "message": f"连接成功，模型响应：{content[:50]}"}
    except Exception as exc:
        return {"success": False, "message": f"连接失败：{exc}"}

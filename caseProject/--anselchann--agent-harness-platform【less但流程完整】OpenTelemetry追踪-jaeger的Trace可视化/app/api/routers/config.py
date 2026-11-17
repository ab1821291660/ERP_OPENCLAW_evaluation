"""Runtime configuration API — set LLM provider at runtime."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.runtime_config import set_llm_config, get_llm_config

router = APIRouter(prefix="/config", tags=["config"])


class LLMConfigRequest(BaseModel):
    api_key: str = Field(default="", description="API key")
    base_url: str = Field(default="", description="API base URL, e.g. https://api.deepseek.com")
    model: str = Field(default="", description="Model name, e.g. deepseek-chat")


@router.get("/llm")
async def get_config():
    """Get current LLM configuration (API key masked)."""
    return get_llm_config()


@router.post("/llm")
async def set_config(body: LLMConfigRequest):
    """Set LLM provider configuration at runtime."""
    result = set_llm_config(
        api_key=body.api_key,
        base_url=body.base_url,
        model=body.model,
    )
    return {"status": "ok", "config": result}

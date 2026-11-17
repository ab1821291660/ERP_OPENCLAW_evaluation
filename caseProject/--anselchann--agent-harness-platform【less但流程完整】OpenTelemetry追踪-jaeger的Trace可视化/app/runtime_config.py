"""
Runtime configuration — mutable settings that can be changed via API at runtime.
"""

from threading import Lock

_lock = Lock()
_state: dict[str, str] = {}


def set_llm_config(api_key: str = "", base_url: str = "", model: str = "") -> dict:
    """Set LLM provider configuration at runtime. Returns updated config."""
    with _lock:
        if api_key:
            _state["llm_api_key"] = api_key
        if base_url:
            _state["llm_base_url"] = base_url
        if model:
            _state["llm_model"] = model
        return get_llm_config()


def get_llm_config() -> dict:
    """Get current LLM config (key masked for safety)."""
    key = _state.get("llm_api_key", "")
    masked = key[:4] + "****" + key[-4:] if len(key) > 8 else ("****" if key else "")
    return {
        "api_key": masked,
        "base_url": _state.get("llm_base_url", ""),
        "model": _state.get("llm_model", ""),
        "configured": bool(key),
    }


def get_llm_api_key() -> str:
    """Get the runtime LLM API key, or fall back to env var."""
    import os
    return _state.get("llm_api_key") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def get_llm_base_url() -> str:
    """Get the runtime LLM base URL, or fall back to env var."""
    import os
    return _state.get("llm_base_url") or os.getenv("LLM_BASE_URL") or ""


def get_llm_model() -> str:
    """Get the runtime LLM model, or fall back to env var."""
    import os
    return _state.get("llm_model") or os.getenv("LLM_MODEL") or "gpt-4.1"

"""
AI Software Engineering Copilot — Gemini Edition
Centralized Google Gemini Service using the official `google-genai` Python SDK.
Handles client initialization, model selection, prompt construction, structured generation,
embeddings, and comprehensive error handling.
"""
import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

logger = logging.getLogger("copilot.gemini_service")

# Centralized Supported Gemini Models
SUPPORTED_GEMINI_MODELS: List[Dict[str, Any]] = [
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "badge": "Default • Fast & Powerful",
        "description": "Recommended for daily coding, rapid generation, automated reviews, and codebase intelligence.",
        "context_window": "1M tokens",
        "is_default": True
    },
    {
        "id": "gemini-2.5-pro",
        "name": "Gemini 2.5 Pro",
        "badge": "Advanced Reasoning",
        "description": "State-of-the-art model for complex architectural analysis, multi-file refactoring, and deep bug hunting.",
        "context_window": "2M tokens",
        "is_default": False
    },
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "badge": "High Throughput",
        "description": "High-speed generation model with low latency.",
        "context_window": "1M tokens",
        "is_default": False
    },
    {
        "id": "gemini-1.5-flash",
        "name": "Gemini 1.5 Flash",
        "badge": "Lightweight",
        "description": "Cost-efficient model for quick code explanations and simple queries.",
        "context_window": "1M tokens",
        "is_default": False
    },
    {
        "id": "gemini-1.5-pro",
        "name": "Gemini 1.5 Pro",
        "badge": "Deep Context",
        "description": "Large context model with high precision.",
        "context_window": "2M tokens",
        "is_default": False
    }
]

# Track active model selection across session
_active_selected_model: Optional[str] = None


class GeminiConfigurationError(Exception):
    """Raised when an operation requires Gemini API key but none is configured."""
    pass


class GeminiModelError(Exception):
    """Raised when an unsupported or invalid model is requested."""
    pass


def get_api_key() -> str:
    """Returns the configured Gemini API key, trimmed."""
    return os.getenv("GEMINI_API_KEY", "").strip()


def is_gemini_configured() -> bool:
    """Returns True if a non-empty GEMINI_API_KEY is configured in the environment."""
    key = get_api_key()
    return bool(key and not key.startswith("your_") and not key.startswith("enter_"))


is_configured = is_gemini_configured


def get_default_model() -> str:
    """Returns the default model from environment variable or system default."""
    env_default = os.getenv("DEFAULT_GEMINI_MODEL", "").strip()
    if env_default and any(m["id"] == env_default for m in SUPPORTED_GEMINI_MODELS):
        return env_default
    return "gemini-2.5-flash"


def get_selected_model() -> str:
    """Returns the currently active user-selected model or the default."""
    global _active_selected_model
    if _active_selected_model and any(m["id"] == _active_selected_model for m in SUPPORTED_GEMINI_MODELS):
        return _active_selected_model
    return get_default_model()


def set_selected_model(model_id: str) -> str:
    """Validates and sets the active model."""
    global _active_selected_model
    cleaned = (model_id or "").strip()
    valid_ids = [m["id"] for m in SUPPORTED_GEMINI_MODELS]
    if cleaned not in valid_ids:
        # If user supplies custom valid gemini model identifier
        if re.match(r"^gemini-[\w\.\-]+$", cleaned):
            _active_selected_model = cleaned
            return cleaned
        raise GeminiModelError(f"Model '{model_id}' is not supported. Must be one of: {', '.join(valid_ids)}")
    _active_selected_model = cleaned
    return cleaned


def get_models_info() -> Dict[str, Any]:
    """Returns current models metadata for frontend model selector."""
    configured = is_gemini_configured()
    active_model = get_selected_model()
    default_model = get_default_model()

    models_list = []
    for m in SUPPORTED_GEMINI_MODELS:
        models_list.append({
            "id": m["id"],
            "name": m["name"],
            "badge": m["badge"],
            "description": m["description"],
            "context_window": m["context_window"],
            "is_default": m["id"] == default_model,
            "is_active": m["id"] == active_model
        })

    return {
        "configured": configured,
        "active_model": active_model,
        "default_model": default_model,
        "models": models_list,
        "setup_required": not configured,
        "setup_message": (
            "Gemini API key is configured and active."
            if configured else
            "GEMINI_API_KEY is not configured in .env. Configure your free API key from https://aistudio.google.com/ to unlock live Google Gemini intelligence."
        )
    }


def get_gemini_client():
    """Initializes and returns the official google-genai Client."""
    if not is_gemini_configured():
        raise GeminiConfigurationError(
            "Google Gemini API key is missing. Add GEMINI_API_KEY to your .env file to enable live AI features."
        )
    if genai is None:
        raise ImportError("google-genai SDK is not installed.")
    return genai.Client(api_key=get_api_key())


def generate_content(
    prompt: str,
    system_instruction: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
    response_mime_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core generation method using the official google-genai SDK.
    """
    if not is_gemini_configured():
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is not configured in .env. Set your key to enable live generation."
        )

    target_model = model or get_selected_model()
    client = get_gemini_client()

    config = None
    if types is not None:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction or "You are an expert AI software engineering copilot.",
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type or "text/plain"
        )

    try:
        response = client.models.generate_content(
            model=target_model,
            contents=prompt,
            config=config
        )

        output_text = getattr(response, "text", "") or ""
        if not output_text.strip():
            raise RuntimeError("Gemini returned an empty response. The prompt may have triggered content moderation.")

        tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens = getattr(response.usage_metadata, "total_token_count", 0) or 0

        return {
            "success": True,
            "text": output_text,
            "model": target_model,
            "provider": "Google Gemini",
            "tokens": tokens
        }

    except Exception as e:
        err_msg = str(e)
        logger.error("Gemini API error (%s): %s", target_model, err_msg)
        if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
            raise RuntimeError(
                "Gemini API rate limit exceeded. Please wait a moment before trying again or choose another model."
            )
        if "API_KEY_INVALID" in err_msg or "PERMISSION_DENIED" in err_msg:
            raise RuntimeError(
                "Invalid Google Gemini API key. Please check your GEMINI_API_KEY in .env."
            )
        raise RuntimeError(f"Gemini API generation error: {err_msg}")


async def generate_content_async(*args, **kwargs) -> Dict[str, Any]:
    """Asynchronous wrapper for generate_content."""
    import asyncio
    return await asyncio.to_thread(generate_content, *args, **kwargs)


def generate_embedding(text: str, model: str = "text-embedding-004") -> Optional[List[float]]:
    """Generates vector embedding for text using Gemini embedding model."""
    if not is_gemini_configured():
        return None

    client = get_gemini_client()
    try:
        resp = client.models.embed_content(
            model=model,
            contents=text
        )
        if resp.embedding and resp.embedding.values:
            return list(resp.embedding.values)
        if hasattr(resp, "embeddings") and resp.embeddings:
            return list(resp.embeddings[0].values)
        return None
    except Exception as e:
        logger.warning("Gemini embedding generation failed (%s): %s", model, e)
        return None

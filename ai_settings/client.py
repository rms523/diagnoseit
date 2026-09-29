"""OpenAI-compatible chat calls shared by AI diagnosis and report review."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import BadRequestError, OpenAI

from .services import AIConfig

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

# Diagnosis and report review run inside web requests, which nginx and gunicorn end after 300 s.
# Stay under that and never retry, so a slow model fails with a clear error instead of a 504.
REQUEST_TIMEOUT_CAP_SECONDS = 270


def openai_client(config: AIConfig) -> OpenAI:
    # Local OpenAI-compatible servers often need no key, but the client requires a value.
    return OpenAI(
        api_key=config.api_key or "not-needed",
        base_url=config.api_base,
        timeout=min(config.timeout_seconds, REQUEST_TIMEOUT_CAP_SECONDS),
        max_retries=0,
    )


def chat_json(
    config: AIConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float = 0.2,
) -> str:
    """Ask for a JSON reply, retrying without response_format for servers that reject it."""
    client = openai_client(config)
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        response = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
    except BadRequestError:
        response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def chat_text(
    config: AIConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float = 0.2,
) -> str:
    """Ask for a written reply. Unlike chat_json, nothing here is parsed: the prose is the answer."""
    response = openai_client(config).chat.completions.create(
        model=config.model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model reply, tolerating markdown fences and surrounding prose."""
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Model reply is not a JSON object")
    return value

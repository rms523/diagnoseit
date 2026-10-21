"""OpenAI-compatible chat calls shared by AI diagnosis and report review."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from openai import BadRequestError, OpenAI

from .services import AIConfig

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
# A reasoning model on a server that does not split its thinking out sends it inline, before the answer.
_THINK_RE = re.compile(r"^\s*<think>.*?</think>", re.DOTALL)

# Calls made inside a web request (report chat, test link suggestions) end when nginx and gunicorn do, after
# 300 s. Stay under that and never retry, so a slow model fails with a clear error instead of a 504. Calls on
# the Celery workers (diagnoses, reviews, prescription reading) pass background=True and use the full setting.
REQUEST_TIMEOUT_CAP_SECONDS = 270


def openai_client(config: AIConfig, *, background: bool = False) -> OpenAI:
    # Local OpenAI-compatible servers often need no key, but the client requires a value.
    return OpenAI(
        api_key=config.api_key or "not-needed",
        base_url=config.api_base,
        timeout=config.timeout_seconds if background else min(config.timeout_seconds, REQUEST_TIMEOUT_CAP_SECONDS),
        max_retries=0,
    )


def chat_json(
    config: AIConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float = 0.2,
    background: bool = False,
) -> str:
    """Ask for a JSON reply, retrying without response_format for servers that reject it."""
    client = openai_client(config, background=background)
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


@dataclass
class StreamProgress:
    """How far a streamed reply has got. Each chunk is counted as one token, which is what servers send."""

    reasoning_tokens: int = 0
    reply_tokens: int = 0

    @property
    def phase(self) -> str:
        if self.reply_tokens:
            return "writing"
        return "thinking" if self.reasoning_tokens else "waiting"


def _reasoning_text(delta: Any) -> str:
    # llama.cpp, vLLM, and LM Studio send a reasoning model's thinking as reasoning_content, Ollama as reasoning.
    for name in ("reasoning_content", "reasoning"):
        value = getattr(delta, name, None)
        if isinstance(value, str) and value:
            return value
    return ""


def stream_chat_json(
    config: AIConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float = 0.2,
    on_progress: Callable[[StreamProgress], None] | None = None,
) -> str:
    """chat_json for background work, streamed.

    The timeout then limits how long the model may go quiet rather than how long the whole reply may take, so a
    slow model that keeps writing is not cut off. on_progress hears about every chunk and may raise to stop.
    """
    client = openai_client(config, background=True)
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    try:
        stream = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
    except BadRequestError:
        stream = client.chat.completions.create(**kwargs)

    progress = StreamProgress()
    parts: list[str] = []
    inline_thinking = False
    # Leaving the block closes the connection, so a stopped diagnosis stops the model server generating too.
    with stream:
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            if delta.content:
                if not parts and delta.content.lstrip().startswith("<think>"):
                    inline_thinking = True
                if inline_thinking:
                    progress.reasoning_tokens += 1
                    # The closing tag can arrive split across chunks.
                    inline_thinking = "</think>" not in (parts[-1] if parts else "") + delta.content
                else:
                    progress.reply_tokens += 1
                parts.append(delta.content)
            elif _reasoning_text(delta):
                progress.reasoning_tokens += 1
            else:
                continue
            if on_progress:
                on_progress(progress)
    return "".join(parts).strip()


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
    cleaned = _FENCE_RE.sub("", _THINK_RE.sub("", text).strip())
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

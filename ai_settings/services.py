"""Resolve AI connection settings: values saved in AI settings first, environment variables otherwise."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, replace
from typing import Any

import requests
from django.db import DatabaseError

from .models import AIServiceConfig

logger = logging.getLogger(__name__)

ROLE_DIAGNOSIS = AIServiceConfig.ROLE_DIAGNOSIS
ROLE_OCR = AIServiceConfig.ROLE_OCR
ROLE_REPORT_REVIEW = AIServiceConfig.ROLE_REPORT_REVIEW
ROLES = [role for role, _ in AIServiceConfig.ROLE_CHOICES]
ROLE_LABELS = dict(AIServiceConfig.ROLE_CHOICES)
OPENAI_DEFAULT_BASE_URL = 'https://api.openai.com/v1'
# Used when a service has no saved temperature. OCR in PaddleOCR mode uses 0 instead.
DEFAULT_TEMPERATURES = {ROLE_DIAGNOSIS: 0.3, ROLE_OCR: 0.1, ROLE_REPORT_REVIEW: 0.1}


@dataclass(frozen=True)
class AIConfig:
    role: str
    source: str  # 'database', 'environment', or 'diagnosis' (report review inheriting AI diagnosis)
    enabled: bool
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    max_tokens: int
    ocr_mode: str = 'auto'
    review_input: str = 'auto'
    auto_review: bool = False  # report review only: review every report after it is parsed
    auto_apply: bool = False  # report review only: apply safe fixes without waiting for the user
    temperature: float | None = None  # None: the caller's default for this service
    parallel_requests: int = 1  # report OCR only: pages sent to the server at once

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.model) and bool(self.base_url or self.api_key)

    def temperature_or(self, default: float) -> float:
        """The saved temperature, or the given default when none is saved."""
        return default if self.temperature is None else self.temperature

    @property
    def api_base(self) -> str:
        """Request base URL; OpenAI's public API when only an API key is configured."""
        if self.base_url:
            return self.base_url.rstrip('/')
        return OPENAI_DEFAULT_BASE_URL if self.provider == AIServiceConfig.PROVIDER_OPENAI else ''


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _normalize_ocr_mode(value: str) -> str:
    value = value.strip().lower()
    if value in ('paddle_ocr', 'ocr', 'paddle'):
        return 'paddle_ocr'
    if value in ('json_vlm', 'json', 'vlm'):
        return 'json_vlm'
    return 'auto'


def environment_config(role: str) -> AIConfig:
    """Settings used before anything is saved for a role."""
    if role == ROLE_DIAGNOSIS:
        return AIConfig(
            role=role,
            source='environment',
            enabled=True,
            provider=AIServiceConfig.PROVIDER_OPENAI,
            base_url=os.getenv('OPENAI_BASE_URL', '').strip().rstrip('/'),
            api_key=os.getenv('OPENAI_API_KEY', '').strip(),
            model=os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo').strip(),
            timeout_seconds=_env_int('OPENAI_TIMEOUT', 120),
            max_tokens=_env_int('OPENAI_MAX_TOKENS', 1000),
        )

    if role == ROLE_OCR:
        provider = os.getenv('VLM_PROVIDER', 'ollama').strip().lower()
        if provider == AIServiceConfig.PROVIDER_OLLAMA:
            base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
            model = os.getenv('OLLAMA_MODEL', 'qwen3-vl:4b')
        else:
            provider = AIServiceConfig.PROVIDER_OPENAI
            base_url = os.getenv('VLM_API_BASE', 'http://localhost:8080/v1')
            model = os.getenv('VLM_MODEL', 'PaddleOCR-VL-1.6 (Vision OCR)')
        return AIConfig(
            role=role,
            source='environment',
            enabled=True,
            provider=provider,
            base_url=base_url.strip().rstrip('/'),
            api_key=os.getenv('VLM_API_KEY', '').strip(),
            model=model.strip(),
            timeout_seconds=_env_int('VLM_TIMEOUT', _env_int('OLLAMA_TIMEOUT', 300)),
            max_tokens=4096,
            ocr_mode=_normalize_ocr_mode(os.getenv('VLM_MODE', 'auto')),
            parallel_requests=max(1, _env_int('VLM_PARALLEL_REQUESTS', 1)),
        )

    if role == ROLE_REPORT_REVIEW:
        # Report review reuses the AI diagnosis connection until it is configured separately.
        diagnosis = get_ai_config(ROLE_DIAGNOSIS)
        return replace(
            diagnosis,
            role=role,
            source='diagnosis',
            timeout_seconds=max(diagnosis.timeout_seconds, 180),
            max_tokens=max(diagnosis.max_tokens, 2000),
            # Reviewing every report costs model calls and applying fixes changes results: both need an explicit choice.
            auto_review=False,
            auto_apply=False,
            # Report review keeps its own default temperature until one is saved for it.
            temperature=None,
        )

    raise ValueError(f'Unknown AI role: {role}')


def get_ai_config(role: str) -> AIConfig:
    """Effective settings for a role, read per call so saved changes apply without restarts."""
    if role not in ROLES:
        raise ValueError(f'Unknown AI role: {role}')
    try:
        row = AIServiceConfig.objects.filter(role=role).first()
    except DatabaseError:
        # The settings table may not exist yet (e.g. new code running before migrate).
        logger.warning('AI settings table unavailable; using environment settings for %s', role)
        row = None

    fallback = environment_config(role)
    if row is None:
        return fallback

    base_url = row.base_url.strip().rstrip('/')
    # A blank saved key keeps the fallback key only for the same server, so a key is never
    # sent to a host it was not configured for.
    api_key = row.api_key or (fallback.api_key if base_url == fallback.base_url else '')
    return AIConfig(
        role=role,
        source='database',
        enabled=row.enabled,
        provider=row.provider,
        base_url=base_url,
        api_key=api_key,
        model=row.model.strip(),
        timeout_seconds=row.timeout_seconds,
        max_tokens=row.max_tokens,
        ocr_mode=row.ocr_mode,
        review_input=row.review_input,
        auto_review=row.auto_review,
        auto_apply=row.auto_apply,
        temperature=row.temperature,
        parallel_requests=row.parallel_requests,
    )


def save_ai_config(role: str, values: dict[str, Any], user) -> AIConfig:
    """Create or update a role's saved settings; the first save starts from the effective values."""
    row = AIServiceConfig.objects.filter(role=role).first()
    if row is None:
        current = get_ai_config(role)
        row = AIServiceConfig(
            role=role,
            enabled=current.enabled,
            provider=current.provider,
            base_url=current.base_url,
            model=current.model,
            timeout_seconds=current.timeout_seconds,
            max_tokens=current.max_tokens,
            ocr_mode=current.ocr_mode,
            review_input=current.review_input,
            auto_review=current.auto_review,
            auto_apply=current.auto_apply,
            temperature=current.temperature,
            parallel_requests=current.parallel_requests,
        )

    values = dict(values)
    clear_api_key = values.pop('clear_api_key', False)
    new_api_key = values.pop('api_key', '')
    previous_server = (row.provider, row.base_url)
    for field, value in values.items():
        setattr(row, field, value)
    # A saved key is never sent to a server it was not saved for: moving to another server needs the key
    # again, so nobody who can edit settings can collect the key by pointing the service at their own server.
    if clear_api_key or (row.pk and (row.provider, row.base_url) != previous_server):
        row.api_key = ''
    if new_api_key:
        row.api_key = new_api_key
    row.updated_by = user
    row.save()
    return get_ai_config(role)


def check_connection(config: AIConfig) -> dict[str, Any]:
    """List the server's models to confirm the URL, API key, and model name."""
    base = config.api_base
    if not base:
        return {'ok': False, 'error': 'Set a base URL first.', 'models': []}

    if config.provider == AIServiceConfig.PROVIDER_OLLAMA:
        url = f'{base}/api/tags'
    else:
        url = f'{base}/models'
    headers = {'Authorization': f'Bearer {config.api_key}'} if config.api_key else {}

    started = time.monotonic()
    try:
        response = requests.get(url, headers=headers, timeout=(10, 20))
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.HTTPError as exc:
        return {'ok': False, 'error': f'{url} returned HTTP {exc.response.status_code}.', 'models': []}
    except requests.exceptions.RequestException as exc:
        return {'ok': False, 'error': f'Could not reach {url} ({type(exc).__name__}).', 'models': []}
    except ValueError:
        return {'ok': False, 'error': f'{url} did not return JSON.', 'models': []}

    if config.provider == AIServiceConfig.PROVIDER_OLLAMA:
        names = [item.get('name') for item in payload.get('models') or [] if isinstance(item, dict)]
    else:
        names = [item.get('id') for item in payload.get('data') or [] if isinstance(item, dict)]
    models = sorted({name for name in names if name})

    result: dict[str, Any] = {
        'ok': True,
        'latency_ms': int((time.monotonic() - started) * 1000),
        'models': models,
    }
    if config.model and models and config.model not in models:
        result['warning'] = f'Model "{config.model}" is not in this server\'s model list.'
    return result

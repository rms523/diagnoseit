"""Asking the AI about one stored document, shared by reports and prescriptions.

The model is told to answer from the document it is given and to say so when the document does not hold
the answer, because the alternative — filling gaps from memory — reads exactly like a real finding. It is
not asked for a diagnosis: the app is not a substitute for a clinician.

What is sent goes through the same redaction the AI review uses (`utils.report_redaction`): the account
holder's name, phone numbers, and emails are replaced, and legal and contact boilerplate is left out. The
conversation is stored on the document itself, so it is there on the next visit, and the most recent turns
are sent back as context, so follow-up questions work.

The AI diagnosis model answers, since it is the service already configured to read health data and reply
in prose; report review inherits that connection the same way (`ai_settings.services`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from rest_framework import status
from rest_framework.response import Response

from ai_settings.client import chat_text
from ai_settings.services import DEFAULT_TEMPERATURES, ROLE_DIAGNOSIS, get_ai_config
from utils.report_redaction import Redactor, is_boilerplate

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 2000
# Kept on the document. Older turns drop off the top, so one conversation cannot grow without limit.
MAX_STORED_MESSAGES = 40
# Turns sent back to the model as context. Enough for follow-ups without crowding out the document itself.
HISTORY_MESSAGES = 16
MAX_REPLY_TOKENS = 1200
# Document text sent with the question. Past this the earliest lines are dropped and the prompt says so.
MAX_TEXT_CHARS = 8000

CLOSING_RULES = (
    "- Answer only from the document you are given. When it does not contain the answer, say so plainly "
    "instead of filling the gap from general knowledge.\n"
    "- Do not name a condition the person has, and do not tell them to start, stop, or change any "
    "treatment. Where something could matter, say it is worth discussing with their doctor.\n"
    "- Be brief and concrete, and quote what you are talking about.\n"
    "- Names, phone numbers, and emails have been replaced with [REDACTED]; do not remark on this."
)


def chat_state(stored: Any) -> dict:
    """The stored conversation, as a dict that is always the right shape."""
    stored = stored if isinstance(stored, dict) else {}
    messages = stored.get('messages')
    return {'messages': [item for item in messages if _is_message(item)] if isinstance(messages, list) else []}


def _is_message(item: object) -> bool:
    return (
        isinstance(item, dict)
        and item.get('role') in ('user', 'assistant')
        and isinstance(item.get('content'), str)
    )


def document_text(raw: object, redactor, limit: int = MAX_TEXT_CHARS) -> str:
    """A document's own text, redacted, without boilerplate, and trimmed to what a prompt can carry."""
    if not isinstance(raw, str) or not raw.strip():
        return ''
    kept = [redactor.line(line) for line in raw.splitlines() if line.strip() and not is_boilerplate(line)]
    text = '\n'.join(kept)
    if len(text) <= limit:
        return text
    # The end of a document carries the comments and interpretation, so the earliest lines go first.
    return '[earlier pages left out to fit]\n' + text[-limit:]


def build_messages(system_prompt: str, context: str, history: list[dict], question: str) -> list[dict[str, str]]:
    """The model request: the rules, the document, the recent turns, then the new question."""
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'system', 'content': context},
        *({'role': item['role'], 'content': item['content']} for item in history[-HISTORY_MESSAGES:]),
        {'role': 'user', 'content': question},
    ]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_turn(instance: Any, field: str, question: str, answer: str) -> dict:
    """Store the question and its answer together, so a failed reply never leaves a dangling question."""
    state = chat_state(getattr(instance, field))
    state['messages'] = (
        state['messages']
        + [{'role': 'user', 'content': question, 'at': _now()},
           {'role': 'assistant', 'content': answer, 'at': _now()}]
    )[-MAX_STORED_MESSAGES:]
    setattr(instance, field, state)
    instance.save(update_fields=[field, 'updated_at'])
    return state


def chat_view(
    request,
    instance: Any,
    *,
    field: str,
    system_prompt: str,
    context: Callable[[], str],
    subject: str,
) -> Response:
    """GET the conversation, POST {question} to ask, DELETE to start over.

    `context` is called only when a question is actually asked, so reading the conversation never costs
    a document read.
    """
    config = get_ai_config(ROLE_DIAGNOSIS)

    def payload() -> dict:
        return {
            'messages': chat_state(getattr(instance, field))['messages'],
            'configured': config.is_configured,
            'model': config.model if config.is_configured else '',
        }

    if request.method == 'GET':
        return Response(payload())

    if request.method == 'DELETE':
        setattr(instance, field, {})
        instance.save(update_fields=[field, 'updated_at'])
        return Response(payload())

    question = str(request.data.get('question') or '').strip()
    if not question:
        return Response({'error': f'Type a question about this {subject}.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(question) > MAX_QUESTION_CHARS:
        return Response(
            {'error': f'Keep the question under {MAX_QUESTION_CHARS} characters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not config.is_configured:
        return Response(
            {'error': f'Set up the AI diagnosis model in AI settings to ask about a {subject}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from django_ratelimit.core import is_ratelimited

    if is_ratelimited(request, group='document-ai-chat', key='user', rate='10/m', increment=True):
        return Response(
            {'error': 'Too many AI questions. Please wait a minute and try again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    history = chat_state(getattr(instance, field))['messages']
    owner = instance.user
    redactor = Redactor([owner.first_name, owner.last_name])
    safe_history = [
        {**item, 'content': redactor.line(item['content'])}
        for item in history
    ]
    safe_question = redactor.line(question)
    try:
        answer = chat_text(
            config,
            build_messages(system_prompt, context(), safe_history, safe_question),
            max_tokens=max(config.max_tokens, MAX_REPLY_TOKENS),
            temperature=config.temperature_or(DEFAULT_TEMPERATURES[ROLE_DIAGNOSIS]),
        )
    except Exception as exc:
        logger.warning('Chat about %s %s failed: %s', subject, instance.pk, exc)
        return Response(
            {'error': f'The AI diagnosis model did not respond ({type(exc).__name__}).'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not answer:
        return Response({'error': 'The model returned an empty reply.'}, status=status.HTTP_502_BAD_GATEWAY)

    save_turn(instance, field, question, answer)
    return Response(payload())

from dataclasses import replace

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import AIServiceConfig
from .serializers import AIServiceConfigUpdateSerializer
from .services import (
    DEFAULT_TEMPERATURES,
    ROLE_DIAGNOSIS,
    ROLE_LABELS,
    ROLE_OCR,
    ROLE_REPORT_REVIEW,
    ROLES,
    check_connection,
    get_ai_config,
    save_ai_config,
)


def _serialize(config):
    row = AIServiceConfig.objects.filter(role=config.role).select_related('updated_by').first()
    return {
        'role': config.role,
        'label': ROLE_LABELS[config.role],
        'source': config.source,
        'enabled': config.enabled,
        'provider': config.provider,
        'base_url': config.base_url,
        'model': config.model,
        'timeout_seconds': config.timeout_seconds,
        'max_tokens': config.max_tokens,
        'temperature': config.temperature,
        'default_temperature': DEFAULT_TEMPERATURES[config.role],
        'parallel_requests': config.parallel_requests,
        'ocr_mode': config.ocr_mode,
        'review_input': config.review_input,
        'auto_review': config.auto_review,
        'auto_apply': config.auto_apply,
        'api_key_set': bool(config.api_key),
        'is_configured': config.is_configured,
        'updated_at': row.updated_at if row else None,
        'updated_by': row.updated_by.username if row and row.updated_by else None,
    }


def _unknown_role():
    return Response({'error': 'Unknown AI service.'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_ai_settings(request):
    """Effective settings for every AI role. Settings are shared by the whole server; administrators maintain them."""
    return Response({'services': [_serialize(get_ai_config(role)) for role in ROLES]})


# Every user can read the settings; only administrators change them or have the server contact a URL,
# since they decide where everyone's reports are sent.
@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAdminUser])
def ai_setting_detail(request, role):
    """Save a role's settings, or DELETE to return it to environment defaults."""
    if role not in ROLES:
        return _unknown_role()

    if request.method == 'DELETE':
        AIServiceConfig.objects.filter(role=role).delete()
        return Response(_serialize(get_ai_config(role)))

    serializer = AIServiceConfigUpdateSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    if role != ROLE_OCR and values.get('provider') == AIServiceConfig.PROVIDER_OLLAMA:
        return Response(
            {'provider': ['Only report OCR supports the Ollama native API.']},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(_serialize(save_ai_config(role, values, request.user)))


@api_view(['POST'])
@permission_classes([IsAdminUser])
def test_ai_setting(request, role):
    """Check a server with saved settings, optionally overridden by unsaved form values."""
    if role not in ROLES:
        return _unknown_role()

    serializer = AIServiceConfigUpdateSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    saved = get_ai_config(role)
    overrides = {field: values[field] for field in ('provider', 'base_url', 'model') if field in values}
    config = replace(saved, **overrides)
    if values.get('api_key'):
        config = replace(config, api_key=values['api_key'])
    elif config.base_url != saved.base_url:
        # Never send the stored key to a server it was not saved for.
        config = replace(config, api_key='')
    return Response(check_connection(config))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_status(request):
    """Which AI features are available, without exposing connection details."""
    review = get_ai_config(ROLE_REPORT_REVIEW)
    diagnosis = get_ai_config(ROLE_DIAGNOSIS)
    ocr = get_ai_config(ROLE_OCR)
    return Response({
        'report_review': {
            'available': review.is_configured,
            'model': review.model if review.is_configured else '',
            # Upload forms start their "review with AI" checkbox from this shared setting.
            'auto_review': review.is_configured and review.auto_review,
        },
        'diagnosis': {'available': diagnosis.is_configured},
        # A report page can ask its AI review to read the pages with the OCR model.
        'ocr': {'available': ocr.is_configured},
    })

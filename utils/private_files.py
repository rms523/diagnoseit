"""Short-lived signed URLs for private medical uploads."""

from urllib.parse import urlencode

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse


_signer = TimestampSigner(salt="diagnoseit.private-medical-file")


def private_file_url(request, view_name: str, object_id: int, file_name: str) -> str:
    token = _signer.sign(f"{object_id}:{file_name}")
    path = f"{reverse(view_name, args=[object_id])}?{urlencode({'token': token})}"
    return request.build_absolute_uri(path) if request is not None else path


def private_file_token_is_valid(token: str, object_id: int, file_name: str) -> bool:
    if not token:
        return False
    max_age = int(getattr(settings, "PRIVATE_FILE_URL_MAX_AGE", 300))
    try:
        payload = _signer.unsign(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return payload == f"{object_id}:{file_name}"

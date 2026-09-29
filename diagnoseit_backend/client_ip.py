"""The address a request came from, for rate limits."""


def client_ip(request) -> str:
    """X-Real-IP from the bundled nginx, which always overwrites it; otherwise the connecting address.

    Only nginx reaches the backend in the self-hosted and production stacks (production publishes the API on
    127.0.0.1 only), so a client cannot choose this value there.
    """
    return request.META.get('HTTP_X_REAL_IP', '').strip() or request.META.get('REMOTE_ADDR', '')

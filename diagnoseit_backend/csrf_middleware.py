import logging
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('django.request')

class LoggingCsrfMiddleware(CsrfViewMiddleware):
    """CSRF middleware with detailed logging"""
    
    def process_view(self, request, callback, callback_args, callback_kwargs):
        logger.info(f"🔒 CSRF CHECK: {request.method} {request.path}")
        logger.debug(f"🔒 CSRF HEADERS: {dict(request.headers)}")
        logger.debug(f"🔒 CSRF COOKIES: {dict(request.COOKIES)}")
        
        # Check if this is an API endpoint
        if request.path.startswith('/api/'):
            logger.info(f"🔒 API ENDPOINT: Skipping CSRF for {request.path}")
            return None
        
        # For non-API endpoints, use normal CSRF processing
        result = super().process_view(request, callback, callback_args, callback_kwargs)
        
        if result:
            logger.error(f"❌ CSRF FAILED: {request.method} {request.path} - {result}")
            logger.error(f"❌ CSRF REASON: {getattr(result, 'content', 'Unknown')}")
        
        return result
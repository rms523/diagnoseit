import logging
import time
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('django.request')

class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware to log all requests and responses"""
    
    def process_request(self, request):
        request.start_time = time.time()
        logger.info(f"REQUEST: {request.method} {request.path} from {request.META.get('REMOTE_ADDR', 'unknown')}")
        return None
    
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            logger.info(f"RESPONSE: {request.method} {request.path} -> {response.status_code} ({duration:.3f}s)")
        return response
    
    def process_exception(self, request, exception):
        logger.error(f"EXCEPTION: {request.method} {request.path} - {type(exception).__name__}: {str(exception)}")
        return None
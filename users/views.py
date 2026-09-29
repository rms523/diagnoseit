from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from datetime import timedelta
from .serializers import UserSerializer, UserUpdateSerializer, ChangePasswordSerializer
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


def _issue_token(user, *, rotate=False):
    """Return a live token, replacing expired or explicitly rotated credentials."""
    token = Token.objects.filter(user=user).first()
    lifetime_days = int(getattr(settings, 'API_TOKEN_TTL_DAYS', 30))
    expired = bool(
        token and lifetime_days > 0
        and token.created < timezone.now() - timedelta(days=lifetime_days)
    )
    if token and (rotate or expired):
        token.delete()
        token = None
    return token or Token.objects.create(user=user)


def _check_ratelimit(request):
    """Return a 429 Response if the request is rate-limited."""
    if getattr(request, 'limited', False):
        return Response(
            {'error': 'Too many requests. Please try again later.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    return None


def registration_open() -> bool:
    """Anyone may create the first account; later ones only when REGISTRATION_OPEN is set."""
    return settings.REGISTRATION_OPEN or not User.objects.exists()


@api_view(['GET'])
@permission_classes([AllowAny])
def registration_status(request):
    """Whether this server accepts new accounts, so the apps can offer sign-up only when it does."""
    return Response({'open': registration_open()})


@method_decorator(ratelimit(key='ip', rate='5/m', block=False), name='dispatch')
class UserRegistrationView(generics.CreateAPIView):
    """View for user registration"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        from django.db import transaction

        resp = _check_ratelimit(request)
        if resp:
            return resp

        if not registration_open():
            return Response(
                {'error': 'Sign-up is closed on this server. Ask its administrator for an account.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            serializer = self.get_serializer(data=request.data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                # The first account administers the server: AI settings and other accounts.
                first = not User.objects.exists()
                user = serializer.save()
                if first:
                    user.is_staff = user.is_superuser = True
                    user.save(update_fields=['is_staff', 'is_superuser'])
                token = _issue_token(user)

            response_data = {
                'user': UserUpdateSerializer(user).data,
                'token': token.key
            }

            logger.info(f"User registered: {user.username} (ID: {user.id})")
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Registration failed: {str(e)}")
            return Response({
                'error': 'Registration failed. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(ratelimit(key='ip', rate='5/m', block=False), name='dispatch')
class UserLoginView(generics.GenericAPIView):
    """View for user login"""
    permission_classes = [AllowAny]

    def post(self, request):
        resp = _check_ratelimit(request)
        if resp:
            return resp

        username = request.data.get('username')
        password = request.data.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                token = _issue_token(user)
                return Response({
                    'user': UserUpdateSerializer(user).data,
                    'token': token.key
                })
            else:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'error': 'Username and password required'}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """View for user profile management"""
    serializer_class = UserUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """View for changing user password"""
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        token = _issue_token(user, rotate=True)
        return Response({'message': 'Password changed successfully', 'token': token.key})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """View for user logout"""
    try:
        request.user.auth_token.delete()
        return Response({'message': 'Logged out successfully'})
    except (Token.DoesNotExist, AttributeError):
        return Response({'error': 'Error logging out'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_csrf_token(request):
    """View to get CSRF token for frontend"""
    token = get_token(request)
    return JsonResponse({'csrfToken': token})

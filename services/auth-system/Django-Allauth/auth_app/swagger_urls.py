import uuid
import json
from django.urls import path, re_path
from django.contrib.auth import get_user_model, login, get_backends
from django.core.files.base import ContentFile
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from auth_app.utils import generate_initials_avatar_svg
from auth_app.events import (
    emit,
    emit_session_snapshot,
    AUTH_PASSWORD_LOGIN_SUCCESS,
)

User = get_user_model()

# ---------------------------
# Serializers
# ---------------------------

class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

class VerifyCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField()

class UserProfileSerializer(serializers.ModelSerializer):
    fullName = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "fullName", "profile_image"]

    def get_fullName(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

# ---------------------------
# In-memory code store (replace with Redis in prod)
# ---------------------------

PASSWORDLESS_CODES = {}

# ---------------------------
# Passwordless: Request Code
# ---------------------------

@swagger_auto_schema(method='post', operation_summary="Request Login Code", request_body=EmailSerializer)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def api_request_code(request):
    email = request.data.get("email")
    if not email:
        return Response({"success": False, "error": "Email required."}, status=400)

    user, created = User.objects.get_or_create(
        email=email.lower(),
        defaults={"username": email.split("@")[0]}
    )

    code = get_random_string(6, allowed_chars="0123456789")
    PASSWORDLESS_CODES[email] = code

    send_mail(
        subject="Your Login Code",
        message=f"Your verification code is: {code}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=True
    )

    return Response({"success": True, "message": "Verification code sent."}, status=200)

# ---------------------------
# Passwordless: Verify Code + JWT + Full Auth Flow
# ---------------------------

@swagger_auto_schema(method='post', operation_summary="Verify Login Code", request_body=VerifyCodeSerializer)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def api_verify_code(request):
    email = request.data.get("email", "").lower()
    code = request.data.get("code", "").strip()
    correlation_id = str(uuid.uuid4())

    if not email or not code:
        return Response({"success": False, "error": "Email and code required."}, status=400)

    stored_code = PASSWORDLESS_CODES.get(email)
    if not stored_code or stored_code != code:
        return Response({"success": False, "error": "Invalid or expired code."}, status=401)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"success": False, "error": "User not found."}, status=404)

    # Remove used code
    PASSWORDLESS_CODES.pop(email, None)

    # Activate user if not active
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])

    # Auto-generate avatar if missing
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username
    if not getattr(user, "profile_image", None):
        filename, buffer = generate_initials_avatar_svg(full_name)
        user.profile_image.save(filename, ContentFile(buffer.getvalue()))
        user.save()

    # Assign backend explicitly
    backends = get_backends()
    if not backends:
        return Response({"success": False, "error": "No authentication backends configured."}, status=500)

    user.backend = f"{backends[0].__module__}.{backends[0].__class__.__name__}"
    login(request, user)
    session_token = request.session.session_key

    # JWT tokens
    refresh = RefreshToken.for_user(user)
    jwt_tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}

    # User payload
    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "fullName": full_name,
        "avatar": user.profile_image.url if getattr(user, "profile_image", None) else None,
        "is_authenticated": True,
    }

    # Emit login event
    emit(
        AUTH_PASSWORD_LOGIN_SUCCESS,
        {
            "user_id": user.id,
            "session_token": session_token,
            "jwt": jwt_tokens,
            "profile": user_data,
        },
    )

    # Emit session snapshot
    emit_session_snapshot(
        user_id=user.id,
        session_id=session_token,
        profile=user_data,
        jwt=jwt_tokens,
        expires_at=request.session.get_expiry_date().isoformat(),
        state="active",
    )

    serializer = UserProfileSerializer(user)
    return Response({
        "success": True,
        "status": "logged_in",
        "user": serializer.data,
        "session_token": session_token,
        "jwt": jwt_tokens,
        "correlation_id": correlation_id
    }, status=200)

# ---------------------------
# Logout
# ---------------------------

@swagger_auto_schema(method='post', operation_summary="Logout")
@api_view(['POST'])
def api_logout(request):
    request.session.flush()
    return Response({"success": True, "message": "Logged out."})

# ---------------------------
# Session Status
# ---------------------------

@swagger_auto_schema(method='get', operation_summary="Check Session Status")
@api_view(['GET'])
def api_session(request):
    if request.user.is_authenticated:
        return Response({
            "success": True,
            "is_authenticated": True,
            "email": request.user.email
        })
    return Response({"success": True, "is_authenticated": False})

# ---------------------------
# Profile
# ---------------------------

@swagger_auto_schema(method='get', operation_summary="Get Profile", responses={200: UserProfileSerializer()})
@api_view(['GET'])
def api_profile(request):
    if not request.user.is_authenticated:
        return Response({"success": False, "error": "Not authenticated."}, status=401)

    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data)

# ---------------------------
# Swagger Schema View
# ---------------------------

schema_view = get_schema_view(
    openapi.Info(
        title="PaulKeys Auth API (Passwordless)",
        default_version='v1.1',
        description="""
## 🔐 PaulKeys Passwordless Auth API

Email-based authentication with 6-digit verification codes.

### Flow
1. POST `/api/request-code/`
2. POST `/api/verify-code/` → returns JWT + login
3. Session becomes authenticated
        """,
        contact=openapi.Contact(email="admin@paulkeys.dev"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

# ---------------------------
# URL Patterns
# ---------------------------

urlpatterns = [
    # Swagger
    re_path(r'^swagger/?$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    re_path(r'^swagger/index.html$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-index'),
    re_path(r'^redoc/?$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),

    # Passwordless API
    path('api/request-code/', api_request_code, name='api-request-code'),
    path('api/verify-code/', api_verify_code, name='api-verify-code'),
    path('api/logout/', api_logout, name='api-logout'),
    path('api/session/', api_session, name='api-session'),
    path('api/profile/', api_profile, name='api-profile'),
]

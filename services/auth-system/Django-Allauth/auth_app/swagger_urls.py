from django.urls import path, re_path
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings

User = get_user_model()

# ---------------------------
# Serializers
# ---------------------------
class SignupSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

class UserProfileSerializer(serializers.ModelSerializer):
    fullName = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    verified = serializers.SerializerMethodField()
    social = serializers.SerializerMethodField()

    bio = serializers.CharField(default="No bio available", allow_blank=True)
    location = serializers.CharField(default="Unknown location", allow_blank=True)
    phone_number = serializers.CharField(source='phone', default="", allow_blank=True)
    street_address = serializers.CharField(source='address', default="", allow_blank=True)
    country = serializers.CharField(default="", allow_blank=True)
    city = serializers.CharField(default="", allow_blank=True)
    state_province = serializers.CharField(source='state', default="", allow_blank=True)
    postal_code = serializers.CharField(default="", allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "fullName", "avatar", "bio", "location",
            "verified", "is_staff", "is_superuser",
            "phone_number", "country", "street_address", "city", "state_province", "postal_code",
            "social"
        ]

    def get_fullName(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_avatar(self, obj):
        try:
            if obj.profile_image and hasattr(obj.profile_image, "url"):
                return obj.profile_image.url
        except Exception:
            pass
        return "https://via.placeholder.com/128"

    def get_verified(self, obj):
        try:
            from allauth.account.models import EmailAddress
            email_record = EmailAddress.objects.get(user=obj, primary=True)
            return email_record.verified
        except Exception:
            return False

    def get_social(self, obj):
        return {
            "facebook": getattr(obj, "facebook_url", "") or "",
            "x": getattr(obj, "x_url", "") or "",
            "linkedin": getattr(obj, "linkedin_url", "") or "",
            "instagram": getattr(obj, "instagram_url", "") or ""
        }


# ---------------------------
# Stateless API Endpoints
# ---------------------------
@swagger_auto_schema(method='post', operation_summary="Signup", request_body=SignupSerializer)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def api_signup(request):
    data = request.data
    username = data.get("username")
    email = data.get("email")
    password1 = data.get("password1")
    password2 = data.get("password2")

    if not all([username, email, password1, password2]):
        return Response({"success": False, "error": "All fields are required."}, status=400)
    if password1 != password2:
        return Response({"success": False, "error": "Passwords do not match."}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({"success": False, "error": "Username already exists."}, status=400)
    if User.objects.filter(email=email).exists():
        return Response({"success": False, "error": "Email already exists."}, status=400)

    user = User.objects.create_user(username=username, email=email, password=password1)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_link = f"{request.build_absolute_uri('/api/verify-email/')}?uid={uid}&token={token}"
    send_mail(
        subject="Verify your email",
        message=f"Click here to verify your email: {verify_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True
    )
    return Response({"success": True, "message": "User created successfully. Verification email sent."}, status=201)

@swagger_auto_schema(method='post', operation_summary="Login (Stateless)", request_body=LoginSerializer)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def api_login(request):
    data = request.data
    username = data.get("username")
    password = data.get("password")

    user = authenticate(request, username=username, password=password)
    if not user:
        return Response({"success": False, "error": "Invalid credentials."}, status=401)

    serializer = UserProfileSerializer(user)
    return Response({
        "success": True,
        "status": "logged_in",
        "message": f"Login successful.",
        "ip": request.META.get("REMOTE_ADDR"),
        "location": "Localhost",
        "user": serializer.data
    }, status=200)

@swagger_auto_schema(method='post', operation_summary="Logout (Stateless)")
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def api_logout(request):
    return Response({"success": True, "message": "Stateless logout successful. Nothing to clear."}, status=200)

@swagger_auto_schema(method='get', operation_summary="Check Session Status")
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_session(request):
    if request.user.is_authenticated:
        return Response({
            "success": True,
            "is_authenticated": True,
            "status": "active",
            "user": {
                "username": request.user.username,
                "email": request.user.email,
            }
        })
    return Response({
        "success": True,
        "is_authenticated": False,
        "status": "inactive"
    })

@swagger_auto_schema(method='get', operation_summary="Get Profile", responses={200: UserProfileSerializer()})
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_profile(request):
    username = request.query_params.get("username")
    user = None

    # Fetch by username or current session
    if username:
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({"success": False, "error": "User not found."}, status=404)
    elif request.user.is_authenticated:
        user = request.user
    else:
        return Response({"success": False, "error": "Provide ?username=<username> or authenticate first."}, status=400)

    serializer = UserProfileSerializer(user)
    return Response({"authenticated": True, "user": serializer.data}, status=200)


@swagger_auto_schema(method='post', operation_summary="Reset Password Request", request_body=EmailSerializer)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def api_reset_password(request):
    email = request.data.get("email")
    if not email:
        return Response({"success": False, "error": "Email required."}, status=400)
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"success": True, "message": "Password reset email sent."})

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_link = f"{request.build_absolute_uri('/api/reset-password-confirm/')}?uid={uid}&token={token}"
    send_mail(
        subject="Password Reset Request",
        message=f"Reset your password here: {reset_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True
    )
    return Response({"success": True, "message": "Password reset email sent."}, status=200)

@swagger_auto_schema(method='post', operation_summary="Resend Verification Email", request_body=EmailSerializer)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def api_resend_activation(request):
    email = request.data.get("email")
    if not email:
        return Response({"success": False, "error": "Email required."}, status=400)
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"success": False, "error": "User not found."}, status=404)

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_link = f"{request.build_absolute_uri('/api/verify-email/')}?uid={uid}&token={token}"
    send_mail(
        subject="Verify Your Email",
        message=f"Click here to verify your email: {verify_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True
    )
    return Response({"success": True, "message": "Verification email resent."}, status=200)

# ---------------------------
# Swagger Schema View
# ---------------------------
schema_view = get_schema_view(
    openapi.Info(
        title="PaulKeys Auth API (Stateless)",
        default_version='v1',
        description="""
## 🔐 PaulKeys Stateless Auth API
Lightweight, CSRF-free, and session-aware authentication system.

### Available Endpoints
| Endpoint | Method | Description |
|-----------|--------|-------------|
| `/api/signup/` | POST | Register new user |
| `/api/login/` | POST | Stateless login |
| `/api/logout/` | POST | Stateless logout |
| `/api/session/` | GET | Check current session |
| `/api/profile/` | GET | Fetch full profile of authenticated user or ?username=<username> |
| `/api/reset-password/` | POST | Send reset password email |
| `/api/resend-activation/` | POST | Resend email verification |
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
    # Swagger Documentation
    re_path(r'^swagger/?$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    re_path(r'^swagger/index.html$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-index'),
    re_path(r'^redoc/?$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),

    # Stateless API Endpoints
    path('api/signup/', api_signup, name='api-signup'),
    path('api/login/', api_login, name='api-login'),
    path('api/logout/', api_logout, name='api-logout'),
    path('api/session/', api_session, name='api-session'),
    path('api/profile/', api_profile, name='api-profile'),
    path('api/reset-password/', api_reset_password, name='api-reset-password'),
    path('api/resend-activation/', api_resend_activation, name='api-resend-activation'),
]

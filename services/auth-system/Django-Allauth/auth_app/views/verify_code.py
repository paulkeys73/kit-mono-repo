# auth_app/views/verify-code.py
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login
from rest_framework_simplejwt.tokens import RefreshToken
from auth_app.models import CustomUser

@csrf_exempt
def verify_code_api(request):
    """
    API endpoint to verify the code and complete onboarding.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body)
        email = payload.get("email", "").strip().lower()
        code = payload.get("code", "").strip()
        if not email or not code:
            return JsonResponse({"error": "Email and code required"}, status=400)

        user = CustomUser.objects.filter(email=email).first()
        if not user:
            return JsonResponse({"error": "User not found"}, status=404)

        verification = user.verifications.filter(is_used=False).order_by("-created_at").first()
        if not verification:
            return JsonResponse({"error": "No verification code found"}, status=404)
        if verification.code != code:
            return JsonResponse({"error": "Invalid code"}, status=400)
        if verification.is_expired():
            return JsonResponse({"error": "Code expired"}, status=400)

        # Mark code used
        verification.is_used = True
        verification.save(update_fields=["is_used"])

        # Activate user
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])

        # Login
        login(request, user, backend="allauth.account.auth_backends.AuthenticationBackend")
        session_id = request.session.session_key
        request.session.save()
        expires_at = request.session.get_expiry_date().isoformat()

        # JWT
        refresh = RefreshToken.for_user(user)
        jwt_tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}

        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "fullName": user.full_name,
            "avatar": user.profile_image.url if user.profile_image else None,
            "is_authenticated": True
        }

        return JsonResponse({
            "message": "Account verified and logged in successfully.",
            "user": user_data,
            "session_id": session_id,
            "jwt": jwt_tokens,
            "expires_at": expires_at
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

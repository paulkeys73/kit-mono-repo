# auth_app/views/session.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from django.utils import timezone
from auth_app.events import emit_session_snapshot, emit_logout


# -----------------------------
# Session Status
# -----------------------------
@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])  # Allow JWT/session auth without CSRF
def session_status_api(request):
    """
    Return session/auth status and basic user info if logged in.
    """
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return JsonResponse({
            "success": True,
            "is_authenticated": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "fullName": f"{user.first_name} {user.last_name}".strip() or user.username,
                "profile_image": getattr(user.profile_image, "url", None),
            }
        })
    return JsonResponse({
        "success": True,
        "is_authenticated": False
    })


# -----------------------------
# Logout
# -----------------------------
@api_view(["POST"])
@csrf_exempt
@permission_classes([AllowAny])
@authentication_classes([])  # JWT/session auth
def logout_api(request):
    """
    Logout the user by:
    1. Blacklisting all JWT refresh tokens
    2. Flushing the Django session
    3. Emitting a session snapshot
    4. Sending an AUTH_LOGOUT event
    """
    try:
        user = request.user
        session_token = request.session.session_key or f"logout_{getattr(user, 'id', 'anon')}_{int(timezone.now().timestamp())}"
        logout_time = timezone.now().isoformat()

        if not (user and user.is_authenticated):
            request.session.flush()
            response = JsonResponse({
                "success": True,
                "message": "Already logged out."
            })
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            response.delete_cookie("sessionid")
            response.delete_cookie("csrftoken")
            return response

        # ----------------------------
        # Blacklist all outstanding JWT refresh tokens
        # ----------------------------
        tokens = OutstandingToken.objects.filter(user=user)
        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)

        # -----------------------------
        # Emit logout session snapshot
        # -----------------------------
        emit_session_snapshot(
            user_id=user.id,
            session_id=session_token,
            profile=None,
            jwt=None,
            expires_at=logout_time,
            state="logged_out",
        )

        # -----------------------------
        # Flush session
        # -----------------------------
        request.session.flush()

        # -----------------------------
        # Emit logout event
        # -----------------------------
        emit_logout(
            user_id=user.id,
            session_id=session_token,
        )

        response = JsonResponse({
            "success": True,
            "message": "Successfully logged out."
        })
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        response.delete_cookie("sessionid")
        response.delete_cookie("csrftoken")
        return response

    except Exception as e:
        return JsonResponse({
            "success": False,
            "message": str(e)
        }, status=500)

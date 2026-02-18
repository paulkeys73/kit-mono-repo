from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from django.utils import timezone
from auth_app.events import emit, emit_session_snapshot, AUTH_LOGOUT

def session_status_view(request):
    return JsonResponse({
        "endpoint": "session_status_view",
        "status": "ok"
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_api(request):
    """
    Logout the user by blacklisting all refresh tokens, flushing the session,
    emitting a logout snapshot, and sending an AUTH_LOGOUT event.
    """
    try:
        user = request.user
        session_token = request.session.session_key

        # ----------------------------
        # Blacklist all JWT refresh tokens
        # -----------------------------
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
            expires_at=timezone.now().isoformat(),
            state="logged_out",
        )

        # -----------------------------
        # Flush Django session
        # -----------------------------
        request.session.flush()

        # -----------------------------
        # Emit logout event
        # -----------------------------
        emit(
            event_name=AUTH_LOGOUT,
            payload={
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "logout_time": timezone.now().isoformat(),
            },
        )

        return JsonResponse({
            "endpoint": "logout_api",
            "status": "ok",
            "message": "Successfully logged out."
        })

    except Exception as e:
        return JsonResponse({
            "endpoint": "logout_api",
            "status": "error",
            "message": str(e)
        }, status=500)

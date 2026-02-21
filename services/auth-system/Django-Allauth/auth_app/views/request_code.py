# auth_app/views/request_code.py

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from auth_app.models import CustomUser
from auth_app.utils import send_passwordless_code
from auth_app.events import emit_passwordless_code_sent


# -------------------------------------------------------
# REQUEST / RESEND VERIFICATION CODE (API)
# -------------------------------------------------------

@csrf_exempt
def request_code_api(request):
    """
    Request or resend passwordless verification code
    for an existing inactive user.
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body)
        email = payload.get("email", "").strip().lower()

        if not email:
            return JsonResponse({"error": "Email required"}, status=400)

        user = CustomUser.objects.filter(email=email).first()

        if not user:
            return JsonResponse({"error": "User not found"}, status=404)

        if user.is_active:
            return JsonResponse(
                {"error": "User already verified. Please login."},
                status=409,
            )

        # Generate new verification
        verification = send_passwordless_code(user)

        # Emit event
        emit_passwordless_code_sent(
            user_id=user.id,
            email=user.email,
            expires_at=verification.expires_at.isoformat(),
        )

        return JsonResponse(
            {
                "message": "Verification code sent successfully.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "fullName": user.full_name,
                },
                "expires_at": verification.expires_at.isoformat(),
            },
            status=200,
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# -------------------------------------------------------
# INTERNAL HELPER (used by signup flow)
# -------------------------------------------------------

def send_verification_code(user: CustomUser):
    verification = send_passwordless_code(user)

    emit_passwordless_code_sent(
        user_id=user.id,
        email=user.email,
        expires_at=verification.expires_at.isoformat(),
        code=verification.code  # ⚠️ dev only
    )

    return verification
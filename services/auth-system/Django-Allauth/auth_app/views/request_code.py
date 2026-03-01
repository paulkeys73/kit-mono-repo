# auth_app/views/request_code.py

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from allauth.account.models import EmailAddress

from auth_app.models import CustomUser
from auth_app.utils import send_passwordless_code
from auth_app.events import emit_passwordless_code_sent


# -------------------------------------------------------
# REQUEST / RESEND VERIFICATION CODE (API)
# -------------------------------------------------------

@csrf_exempt
def request_code_api(request):
    """
    Request or resend signup verification code.
    If the user does not exist, create an inactive user first.
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    try:
        email = payload.get("email", "").strip().lower()
        requested_username = payload.get("username", "").strip()
        first_name = (payload.get("first_name") or payload.get("firstName") or "").strip()
        last_name = (payload.get("last_name") or payload.get("lastName") or "").strip()

        if not email:
            return JsonResponse({"error": "Email required"}, status=400)

        user = CustomUser.objects.filter(email=email).first()
        created = False

        if not user:
            base_username = requested_username or email.split("@")[0] or "user"
            username = base_username
            counter = 1
            while CustomUser.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            user = CustomUser.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=False,
            )
            created = True

        if user.is_active:
            return JsonResponse(
                {"error": "User already verified. Please login."},
                status=409,
            )

        # Keep allauth email record aligned for verification flow.
        EmailAddress.objects.update_or_create(
            user=user,
            email=email,
            defaults={"primary": True, "verified": False},
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
                "created": created,
                "expires_at": verification.expires_at.isoformat(),
            },
            status=201 if created else 200,
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

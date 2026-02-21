# auth_app/views/signup.py
# auth_app/views/signup.py

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from allauth.account.models import EmailAddress

from auth_app.models import CustomUser
from auth_app.events import (
    emit_user_created,
    emit_passwordless_code_sent,
)
from auth_app.utils import generate_initials_avatar_svg
from auth_app.views.request_code import send_verification_code


@csrf_exempt
def signup_api(request):
    """
    Unified signup endpoint.

    - If user exists and NOT verified → resend verification code
    - If user exists and verified → block
    - If new user → create + send verification code
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body)

        first_name = payload.get("first_name", "").strip()
        last_name = payload.get("last_name", "").strip()
        email = payload.get("email", "").strip().lower()
        username = payload.get("username", "").strip()
        password = payload.get("password", "").strip()
        confirm_password = payload.get("confirm_password", "").strip()

        if not email:
            return JsonResponse({"error": "Email required"}, status=400)

        if password:
            if not first_name or not last_name:
                return JsonResponse(
                    {"error": "First name and last name required for password signup"},
                    status=400,
                )
            if password != confirm_password:
                return JsonResponse({"error": "Passwords do not match"}, status=400)

        # -----------------------------------------
        # EXISTING USER LOGIC
        # -----------------------------------------
        existing_user = CustomUser.objects.filter(email=email).first()

        if existing_user:
            email_record = EmailAddress.objects.filter(
                user=existing_user, email=email
            ).first()

            if email_record and not email_record.verified:
                # Account exists but not verified → resend code
                verification = send_verification_code(existing_user)

                emit_passwordless_code_sent(
                    user_id=existing_user.id,
                    email=existing_user.email,
                    expires_at=verification.expires_at.isoformat(),
                )

                return JsonResponse(
                    {
                        "message": "Account exists but not verified. Verification code resent.",
                        "user": {
                            "id": existing_user.id,
                            "username": existing_user.username,
                            "email": existing_user.email,
                            "fullName": existing_user.full_name,
                        },
                        "expires_at": verification.expires_at.isoformat(),
                    },
                    status=200,
                )

            # Already verified → block duplicate signup
            return JsonResponse(
                {"error": "Email already registered and verified. Please login."},
                status=400,
            )

        # -----------------------------------------
        # USERNAME AUTO-GENERATION
        # -----------------------------------------
        if not username:
            if first_name and last_name:
                base = f"{first_name}{last_name}".lower()
            else:
                base = email.split("@")[0]

            username = base
            counter = 1

            while CustomUser.objects.filter(username=username).exists():
                username = f"{base}{counter}"
                counter += 1

        elif CustomUser.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already in use"}, status=400)

        # -----------------------------------------
        # CREATE USER (INACTIVE UNTIL VERIFIED)
        # -----------------------------------------
        with transaction.atomic():

            user = CustomUser.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=False,  # critical
            )

            if password:
                user.set_password(password)
                method = "password"
            else:
                user.set_unusable_password()
                method = "passwordless"

            user.save()

            EmailAddress.objects.update_or_create(
                user=user,
                email=email,
                defaults={
                    "primary": True,
                    "verified": False,
                },
            )

            # Optional avatar generation
            if first_name and last_name and not user.profile_image:
                filename, buffer = generate_initials_avatar_svg(user.full_name)
                user.profile_image.save(filename, buffer.getvalue())

        # -----------------------------------------
        # SEND VERIFICATION CODE
        # -----------------------------------------
        verification = send_verification_code(user)

        emit_passwordless_code_sent(
            user_id=user.id,
            email=user.email,
            expires_at=verification.expires_at.isoformat(),
        )

        emit_user_created(
            user_id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            method=method,
        )

        return JsonResponse(
            {
                "message": "Signup successful. Verification code sent.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "fullName": user.full_name,
                },
                "expires_at": verification.expires_at.isoformat(),
            },
            status=201,
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
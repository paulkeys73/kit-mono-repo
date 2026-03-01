import json

from allauth.account.models import EmailAddress
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from auth_app.events import emit_passwordless_code_sent, emit_user_created
from auth_app.models import CustomUser
from auth_app.utils import generate_initials_avatar_svg
from auth_app.views.request_code import send_verification_code


def _resolve_username(*, email: str, requested_username: str, first_name: str, last_name: str, exclude_user_id=None) -> str:
    if requested_username:
        base = requested_username
    elif first_name and last_name:
        base = f"{first_name}{last_name}".lower()
    else:
        base = email.split("@")[0] or "user"

    username = base
    counter = 1
    while True:
        query = CustomUser.objects.filter(username=username)
        if exclude_user_id is not None:
            query = query.exclude(pk=exclude_user_id)
        if not query.exists():
            return username
        username = f"{base}{counter}"
        counter += 1


@csrf_exempt
def signup_api(request):
    """
    Unified signup endpoint.

    - If user exists and not verified -> update data and resend verification code
    - If user exists and verified -> block duplicate signup
    - If new user -> create + send verification code
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    try:
        first_name = (payload.get("first_name") or payload.get("firstName") or "").strip()
        last_name = (payload.get("last_name") or payload.get("lastName") or "").strip()
        email = payload.get("email", "").strip().lower()
        requested_username = payload.get("username", "").strip()

        # Support both old and new client payloads.
        password = (payload.get("password") or payload.get("password1") or "").strip()
        confirm_password = (payload.get("confirm_password") or payload.get("password2") or "").strip()

        if not email:
            return JsonResponse({"error": "Email required"}, status=400)

        if confirm_password and not password:
            return JsonResponse({"error": "Password required"}, status=400)

        if password and confirm_password and password != confirm_password:
            return JsonResponse({"error": "Passwords do not match"}, status=400)

        existing_user = CustomUser.objects.filter(email=email).first()

        if existing_user:
            email_record = EmailAddress.objects.filter(user=existing_user, email=email).first()

            if not email_record or not email_record.verified:
                update_fields = []

                if requested_username and requested_username != existing_user.username:
                    resolved_username = _resolve_username(
                        email=email,
                        requested_username=requested_username,
                        first_name=first_name,
                        last_name=last_name,
                        exclude_user_id=existing_user.pk,
                    )
                    if resolved_username != requested_username:
                        return JsonResponse({"error": "Username already in use"}, status=400)
                    existing_user.username = resolved_username
                    update_fields.append("username")

                if first_name and first_name != existing_user.first_name:
                    existing_user.first_name = first_name
                    update_fields.append("first_name")

                if last_name and last_name != existing_user.last_name:
                    existing_user.last_name = last_name
                    update_fields.append("last_name")

                if password:
                    existing_user.set_password(password)
                    update_fields.append("password")

                if update_fields:
                    existing_user.save(update_fields=update_fields)

                EmailAddress.objects.update_or_create(
                    user=existing_user,
                    email=email,
                    defaults={"primary": True, "verified": False},
                )

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

            return JsonResponse(
                {"error": "Email already registered and verified. Please login."},
                status=400,
            )

        username = _resolve_username(
            email=email,
            requested_username=requested_username,
            first_name=first_name,
            last_name=last_name,
        )

        with transaction.atomic():
            user = CustomUser.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=False,
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
                defaults={"primary": True, "verified": False},
            )

            if first_name and last_name and not user.profile_image:
                filename, buffer = generate_initials_avatar_svg(user.full_name)
                user.profile_image.save(filename, ContentFile(buffer.getvalue()), save=False)
                user.save(update_fields=["profile_image"])

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

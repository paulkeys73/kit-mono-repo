import uuid
import json
import random
from datetime import timedelta

from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import (
    get_user_model,
    login as auth_login,
    authenticate,
)
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from auth_app.models import EmailVerification
from auth_app.utils import generate_initials_avatar_svg

# 🔥 Updated event imports
from auth_app.events import (
    emit_passwordless_code_sent,
    emit_passwordless_verified,
    emit_passwordless_failed,
    emit_passwordless_expired,
    emit_password_login_success,
    emit_password_login_failed,
    emit_session_created,
    emit_session_snapshot,
)

User = get_user_model()


# ============================================================
# PASSWORDLESS LOGIN (2-STEP)
# ============================================================

@csrf_exempt
def passwordless_login_api(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip().lower()
        code = data.get("code", "").strip()

        if not email:
            return JsonResponse({"success": False, "message": "Email required"}, status=400)

        # ----------------------------------------------------
        # STEP 1 → SEND CODE
        # ----------------------------------------------------
        if not code:
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email.split("@")[0],
                    "is_active": False,
                },
            )

            numeric_code = str(random.randint(100000, 999999))

            expires_at = timezone.now() + timedelta(minutes=10)

            EmailVerification.objects.create(
                user=user,
                code=numeric_code,
                expires_at=expires_at,
            )

            send_mail(
                subject="Your Verification Code",
                message=f"Use this code to continue: {numeric_code}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

            # 🔥 Emit clean passwordless event
            emit_passwordless_code_sent(
                user_id=user.id,
                email=user.email,
                expires_at=expires_at.isoformat(),
            )

            return JsonResponse({
                "success": True,
                "status": "code_sent",
                "expires_at": expires_at.isoformat(),
                "message": f"Verification code sent to {email}",
            }, status=200)

        # ----------------------------------------------------
        # STEP 2 → VERIFY CODE
        # ----------------------------------------------------
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({"success": False, "message": "User not found"}, status=404)

        verification = EmailVerification.objects.filter(
            user=user,
            code=code,
            is_used=False,
        ).order_by("-created_at").first()

        if not verification:
            emit_passwordless_failed(user.id, "invalid_code")
            return JsonResponse({"success": False, "message": "Invalid code"}, status=400)

        if verification.expires_at <= timezone.now():
            emit_passwordless_expired(user.id)
            return JsonResponse({"success": False, "message": "Code expired"}, status=400)

        verification.is_used = True
        verification.save(update_fields=["is_used"])

        # Activate user
        user.is_active = True
        user.save(update_fields=["is_active"])

        # Login
        auth_login(request, user)
        session_id = request.session.session_key

        # JWT
        refresh = RefreshToken.for_user(user)
        jwt_tokens = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

        full_name = f"{user.first_name} {user.last_name}".strip() or user.username

        if not user.profile_image:
            filename, buffer = generate_initials_avatar_svg(full_name)
            user.profile_image.save(filename, ContentFile(buffer.getvalue()))
            user.save()

        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": full_name,
            "avatar": user.profile_image.url if user.profile_image else "/static/default_avatar.svg",
            "is_authenticated": True,
        }

        # 🔥 Emit proper event chain (correct order)
        emit_passwordless_verified(user.id, session_id)

        emit_session_created(
            user_id=user.id,
            session_id=session_id,
            profile=user_data,
            jwt=jwt_tokens,
            expires_at=request.session.get_expiry_date().isoformat(),
            method="passwordless",
        )

        emit_session_snapshot(
            user_id=user.id,
            session_id=session_id,
            profile=user_data,
            jwt=jwt_tokens,
            expires_at=request.session.get_expiry_date().isoformat(),
            state="active",
        )

        return JsonResponse({
            "success": True,
            "status": "logged_in",
            "user": user_data,
            "session_id": session_id,
            "jwt": jwt_tokens,
            "expires_at": request.session.get_expiry_date().isoformat(),
        })

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


# ============================================================
# PASSWORD LOGIN
# ============================================================

@csrf_exempt
def password_login_api(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
        identifier = data.get("username") or data.get("email")
        password = data.get("password")

        if not identifier or not password:
            return JsonResponse(
                {"success": False, "message": "Username/email and password required"},
                status=400,
            )

        try:
            if "@" in identifier:
                user_obj = User.objects.get(email=identifier)
                username = user_obj.username
            else:
                username = identifier
        except User.DoesNotExist:
            emit_password_login_failed(0, "user_not_found")
            return JsonResponse({"success": False, "message": "Invalid credentials"}, status=401)

        user = authenticate(request, username=username, password=password)
        if not user:
            emit_password_login_failed(user_obj.id, "invalid_password")
            return JsonResponse({"success": False, "message": "Invalid credentials"}, status=401)

        auth_login(request, user)
        session_id = request.session.session_key

        refresh = RefreshToken.for_user(user)
        jwt_tokens = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

        full_name = f"{user.first_name} {user.last_name}".strip() or user.username

        if not user.profile_image:
            filename, buffer = generate_initials_avatar_svg(full_name)
            user.profile_image.save(filename, ContentFile(buffer.getvalue()))
            user.save()

        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": full_name,
            "avatar": user.profile_image.url if user.profile_image else "/static/default_avatar.svg",
            "is_authenticated": True,
        }

        # 🔥 Correct event chain
        emit_password_login_success(user.id, session_id)

        emit_session_created(
            user_id=user.id,
            session_id=session_id,
            profile=user_data,
            jwt=jwt_tokens,
            expires_at=request.session.get_expiry_date().isoformat(),
            method="password",
        )

        emit_session_snapshot(
            user_id=user.id,
            session_id=session_id,
            profile=user_data,
            jwt=jwt_tokens,
            expires_at=request.session.get_expiry_date().isoformat(),
            state="active",
        )

        return JsonResponse({
            "success": True,
            "status": "logged_in",
            "user": user_data,
            "session_id": session_id,
            "jwt": jwt_tokens,
            "expires_at": request.session.get_expiry_date().isoformat(),
        })

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)
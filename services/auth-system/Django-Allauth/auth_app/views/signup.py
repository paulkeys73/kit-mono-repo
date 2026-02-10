import json

from django.conf import settings
from django.core.mail import send_mail
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.shortcuts import redirect
from django.template.loader import render_to_string

from allauth.account.models import EmailAddress, EmailConfirmation

from auth_app.models import CustomUser
from auth_app.utils import generate_initials_avatar_svg
from auth_app.events import emit, AUTH_USER_CREATED


# -------------------------------------------------
# SIGNUPs
# --------------------------------------------------
@csrf_exempt
def signup_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body)

        first_name = payload.get("first_name", "").strip()
        last_name = payload.get("last_name", "").strip()
        email = payload.get("email", "").strip().lower()
        password = payload.get("password", "")
        confirm_password = payload.get("confirm_password", "")
        username = payload.get("username", "").strip()

        # ----------------- VALIDATION -----------------
        if not all([first_name, last_name, email, password, confirm_password]):
            return JsonResponse({"error": "All fields are required"}, status=400)

        if password != confirm_password:
            return JsonResponse({"error": "Passwords do not match"}, status=400)

        if CustomUser.objects.filter(email=email).exists():
            return JsonResponse({"error": "Email already in use"}, status=400)

        # Auto-generate username
        if not username:
            base = f"{first_name}{last_name}".lower()
            username = base
            counter = 1
            while CustomUser.objects.filter(username=username).exists():
                username = f"{base}{counter}"
                counter += 1

        # ----------------- DEFAULT FIELDS -----------------
        defaults = {
            "phone": payload.get("phone", "+995558115396"),
            "bio": payload.get("bio", "Welcome to my profile!"),
            "location": payload.get("location", "Georgia"),
            "address": payload.get("address", "4 shalva gogidze street"),
            "city": payload.get("city", "Digomi"),
            "state": payload.get("state", "Tbilisi"),
            "postal_code": payload.get("postal_code", "0102"),
            "country": payload.get("country", "Georgia"),

            "facebook_url": payload.get("facebook", "https://www.facebook.com/official.paulkeys"),
            "x_url": payload.get("x", "https://x.com/PaulKeys17"),
            "linkedin_url": payload.get(
                "linkedin",
                "https://www.linkedin.com/in/wordpress-developer-full-stack-dev/"
            ),
            "instagram_url": payload.get(
                "instagram",
                "https://www.instagram.com/paul_keys_music_dev"
            ),
        }

        # ----------------- CREATE USER -----------------
        with transaction.atomic():
            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                **defaults
            )

            # Avatar
            if "profile_image" in request.FILES:
                user.profile_image = request.FILES["profile_image"]
            elif not user.profile_image:
                filename, buffer = generate_initials_avatar_svg(user.full_name)
                user.profile_image.save(
                    filename,
                    ContentFile(buffer.getvalue()),
                    save=False
                )

            user.save()

            # ----------------- EMAIL VERIFICATION -----------------
            email_address = EmailAddress.objects.create(
                user=user,
                email=email,
                primary=True,
                verified=False
            )

            confirmation = EmailConfirmation.create(email_address)
            confirmation.sent = timezone.now()
            confirmation.save()

        confirm_link = request.build_absolute_uri(
            f"/verify-email/{confirmation.key}/"
        )

        send_mail(
            subject="Verify your email",
            message=f"Hi {user.username}, verify your account:\n{confirm_link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        # ----------------- EVENT BUS -----------------
        emit(
            AUTH_USER_CREATED,
            {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "country": user.country,
                "city": user.city,
                "timestamp": timezone.now().isoformat(),
            }
        )

        return JsonResponse(
            {
                "message": "Signup successful. Verification email sent.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "fullName": user.full_name,
                    "avatar": user.profile_image.url if user.profile_image else None,
                },
            },
            status=201,
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# --------------------------------------------------
# EMAIL CONFIRMATION CALLBACK
# --------------------------------------------------
def email_confirmed_view(request, key):
    try:
        confirmation = EmailConfirmation.objects.get(key=key)
        confirmation.confirm(request)

        return redirect(settings.LOGIN_REDIRECT_URL)

    except EmailConfirmation.DoesNotExist:
        return HttpResponse("Invalid or expired confirmation link", status=400)


# --------------------------------------------------
# RESEND ACTIVATION EMAIL
# --------------------------------------------------
@csrf_exempt
def resend_activation_email(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    payload = json.loads(request.body)
    email = payload.get("email", "").strip().lower()

    try:
        email_address = EmailAddress.objects.get(email=email, verified=False)

        confirmation = EmailConfirmation.create(email_address)
        confirmation.sent = timezone.now()
        confirmation.save()

        confirm_link = request.build_absolute_uri(
            f"/verify-email/{confirmation.key}/"
        )

        send_mail(
            subject="Verify your email",
            message=f"Verify your account:\n{confirm_link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )

        return JsonResponse({"message": "Verification email resent"})

    except EmailAddress.DoesNotExist:
        return JsonResponse({"error": "No unverified email found"}, status=404)

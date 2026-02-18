import uuid
import json
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login as auth_login, get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from rest_framework_simplejwt.tokens import RefreshToken

from auth_app.utils import generate_initials_avatar_svg
from auth_app.events import emit, emit_session_snapshot, AUTH_LOGIN_SUCCESS

User = get_user_model()


@csrf_exempt
def login_api(request):
    """Authenticate user, return tokens, and emit full login event without exposing password."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required"}, status=400)

    try:
        # ---------------------------------------
        # If already logged in -> block new login
        # ---------------------------------------
        if request.user.is_authenticated:
            session_token = request.session.session_key
            user = request.user

            full_name = f"{user.first_name} {user.last_name}".strip() or user.username

            user_data = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "full_name": full_name,
                "phone": user.phone or "+0000000000",
                "bio": user.bio or "Welcome to my profile!",
                "location": user.location or "Localhost",
                "country": user.country or "Unknown",
                "address": user.address or "Not provided",
                "state": user.state or "Not provided",
                "city": user.city or "Not provided",
                "postal_code": user.postal_code or "0000",
                "facebook": user.facebook_url or "https://www.facebook.com/",
                "x": user.x_url or "https://x.com/",
                "linkedin": user.linkedin_url or "https://www.linkedin.com/",
                "instagram": user.instagram_url or "https://www.instagram.com/",
                "avatar": user.profile_image.url if user.profile_image else "/static/default_avatar.svg",
                "is_authenticated": True,
            }

            return JsonResponse({
                "success": True,
                "status": "already_logged_in",
                "message": "You are already logged in.",
                "user": user_data,
                "session_token": session_token
            }, status=200)

        # ---------------------------------------
        # Parse input
        # ---------------------------------------
        data = json.loads(request.body)
        identifier = data.get("username") or data.get("email")
        password = data.get("password")
        correlation_id = data.get("correlation_id") or str(uuid.uuid4())

        if not identifier or not password:
            return JsonResponse(
                {"success": False, "message": "Username/email and password required"},
                status=400,
            )

        # ---------------------------------------
        # Resolve user by email or username
        # ---------------------------------------
        try:
            if "@" in identifier:
                user_obj = User.objects.get(email=identifier)
                username = user_obj.username
            else:
                username = identifier
        except User.DoesNotExist:
            return JsonResponse({"success": False, "message": "Invalid credentials"}, status=401)

        # ---------------------------------------
        # Authenticate
        # ---------------------------------------
        user = authenticate(request, username=username, password=password)
        if not user:
            return JsonResponse({"success": False, "message": "Invalid credentials"}, status=401)

        # ---------------------------------------
        # Email verification (if allauth installed)
        # ---------------------------------------
        email_qs = getattr(user, "emailaddress_set", None)
        if email_qs:
            first_email = email_qs.first()
            if first_email and not first_email.verified:
                return JsonResponse(
                    {"success": False, "message": "Email not verified. Please check your inbox."},
                    status=403,
                )

        # ---------------------------------------
        # Start session login
        # ---------------------------------------
        auth_login(request, user)
        session_token = request.session.session_key

        # ---------------------------------------
        # IP + Location
        # ---------------------------------------
        ip = request.META.get("REMOTE_ADDR", "127.0.0.1")
        location = "Localhost" if ip in ["127.0.0.1", "localhost"] or settings.DEBUG else "Unknown"

        if ip not in ["127.0.0.1", "localhost"] and not settings.DEBUG:
            try:
                r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5)
                if r.status_code == 200:
                    loc = r.json()
                    location = ", ".join(
                        filter(None, [loc.get("city"), loc.get("region"), loc.get("country_name")])
                    ) or location
            except:
                pass

        user.location = location
        user.save(update_fields=["location"])

        # ---------------------------------------
        # Login notification email
        # ---------------------------------------
        html_message = render_to_string(
            "emails/login.html",
            {"username": user.username, "ip": ip, "location": location},
        )
        send_mail(
            subject="New Login Notification",
            message=f"Hi {user.username}, you logged in. IP: {ip}, Location: {location}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )

        # ---------------------------------------
        # Avatar auto-generation
        # ---------------------------------------
        full_name = f"{user.first_name} {user.last_name}".strip() or user.username
        if not user.profile_image:
            filename, buffer = generate_initials_avatar_svg(full_name)
            user.profile_image.save(filename, ContentFile(buffer.getvalue()))
            user.save()

        # ---------------------------------------
        # JWT tokens
        # ---------------------------------------
        refresh = RefreshToken.for_user(user)
        jwt_tokens = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

        # ---------------------------------------
        # Build payload
        # ---------------------------------------
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": full_name,
            "phone": user.phone or "+0000000000",
            "bio": user.bio or "Welcome to my profile!",
            "location": location,
            "country": user.country or "Unknown",
            "address": user.address or "Not provided",
            "state": user.state or "Not provided",
            "city": user.city or "Not provided",
            "postal_code": user.postal_code or "0000",
            "facebook": user.facebook_url or "https://www.facebook.com/",
            "x": user.x_url or "https://x.com/",
            "linkedin": user.linkedin_url or "https://www.linkedin.com/",
            "instagram": user.instagram_url or "https://www.instagram.com/",
            "avatar": user.profile_image.url if user.profile_image else "/static/default_avatar.svg",
            "is_authenticated": True,
        }

        # ---------------------------------------
        # Emit login event (notification only)
        # ---------------------------------------
        emit(
            AUTH_LOGIN_SUCCESS,
            {
                "user_id": user.id,
                "session_token": session_token,
                "jwt": jwt_tokens,
                "profile": user_data,
            },
        )

        # ---------------------------------------
        # Emit session snapshot (replayable state)
        # ---------------------------------------
        emit_session_snapshot(
            user_id=user.id,
            session_id=session_token,
            profile=user_data,
            jwt=jwt_tokens,
            expires_at=request.session.get_expiry_date().isoformat(),
            state="active",
        )

        # ---------------------------------------
        # Return response
        # ---------------------------------------
        return JsonResponse(
            {
                "success": True,
                "status": "logged_in",
                "message": "Login successful.",
                "user": user_data,
                "session_token": session_token,
                "jwt": jwt_tokens,
                "correlation_id": correlation_id,
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)

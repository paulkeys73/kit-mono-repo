from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from auth_app.events import emit_profile_refresh  # use new helper

@login_required
@require_GET
@ensure_csrf_cookie
def send_profile_to_rabbitmq(request):
    """
    Returns user profile JSON and emits refresh event to RabbitMQ.
    Ensures frontend maintains auth state on refresh with consistent fields.
    Does NOT include JWT tokens for security.
    """
    user = request.user

    # ----------------------------
    # Build consistent profile data with exact fields
    # ----------------------------
    profile_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,

        # NEW — send actual fields
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",

        # Keep your combined version too
        "full_name": f"{user.first_name} {user.last_name}".strip() or user.username,

        "phone": getattr(user, "phone", "+0000000000"),
        "bio": getattr(user, "bio", "Welcome to my profile!"),
        "location": getattr(user, "location", "Localhost"),
        "country": getattr(user, "country", "Unknown"),
        "address": getattr(user, "address", "Not provided"),
        "state": getattr(user, "state", "Not provided"),
        "city": getattr(user, "city", "Not provided"),
        "postal_code": getattr(user, "postal_code", "0000"),

        "facebook": getattr(user, "facebook_url", "https://www.facebook.com/"),
        "x": getattr(user, "x_url", "https://x.com/"),
        "linkedin": getattr(user, "linkedin_url", "https://www.linkedin.com/"),
        "instagram": getattr(user, "instagram_url", "https://www.instagram.com/"),

        "avatar": (
            user.profile_image.url
            if getattr(user, "profile_image", None)
            else "/static/default_avatar.svg"
        ),

        "is_authenticated": True,
    }

    # ----------------------------
    # Emit refresh event via events.py helper
    # ----------------------------
    emit_profile_refresh(
        user_id=user.id,
        session_id=request.session.session_key,
        profile=profile_data,
        jwt=None,  # ensure JWT tokens are not included
    )

    # ----------------------------
    # Return profile only, no JWT tokens
    # ----------------------------
    return JsonResponse({
        "success": True,
        "status": "profile_refreshed",
        "message": "Profile refresh successful.",
        "user": profile_data,
        "session_token": request.session.session_key,
    })

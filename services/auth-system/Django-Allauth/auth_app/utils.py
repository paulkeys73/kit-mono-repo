# auth_app/utils.py
# auth_app/utils.py
import io
from datetime import timedelta
from django.utils.crypto import get_random_string
from django.utils import timezone

from auth_app.events import emit_passwordless_code_sent


# ----------------- SVG AVATAR -----------------
def generate_initials_avatar_svg(full_name: str, size=256):
    """
    Generate a simple SVG avatar with initials.
    Returns: (filename, svg_bytes_io)
    """
    initials = "".join([n[0].upper() for n in full_name.split() if n])
    bg_color = "#2BDE73"
    text_color = "white"
    font_size = int(size / 2)

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">
    <rect width="100%" height="100%" fill="{bg_color}"/>
    <text x="50%" y="50%" dy=".35em" font-family="Arial, sans-serif" font-size="{font_size}" fill="{text_color}" text-anchor="middle">{initials}</text>
    </svg>"""

    buffer = io.BytesIO(svg_content.encode("utf-8"))
    filename = f"avatars/{full_name.replace(' ', '_').lower()}_{get_random_string(6)}.svg"

    return filename, buffer


# ----------------- PASSWORDLESS CODE -----------------
def send_passwordless_code(user):
    """
    Create a new verification code for the user and emit an event.
    Invalidates any previous codes automatically via EmailVerification.create_for_user.
    Returns the EmailVerification instance.
    """
    # Deferred import to avoid circular dependency
    from auth_app.models import EmailVerification

    verification = EmailVerification.create_for_user(user)
    emit_passwordless_code_sent(
        user_id=user.id,
        email=user.email,
        expires_at=verification.expires_at.isoformat()
    )
    return verification
# E:\auth-system\Django-Allauth\auth_app\avatar.py
from django.http import HttpResponse
import hashlib
import random

def generate_initials(full_name: str) -> str:
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return full_name[0].upper()


def initials_avatar_svg(request, username):
    # can adjust this later to load from DB if needed
    initials = generate_initials(username)

    # Generate a deterministic color from the names
    color_seed = int(hashlib.sha256(username.encode()).hexdigest(), 16)
    random.seed(color_seed)
    bg_color = f"hsl({random.randint(0, 360)}, 70%, 50%)"

    svg = f"""
    <svg width="128" height="128" xmlns="http://www.w3.org/2000/svg">
        <rect width="128" height="128" fill="{bg_color}" rx="16" />
        <text x="50%" y="50%" font-size="48" font-family="Arial, sans-serif"
              fill="white" dy=".35em" text-anchor="middle">{initials}</text>
    </svg>
    """

    return HttpResponse(svg, content_type="image/svg+xml")




# auth_app/api_views.py
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie

# ---------------- CSRF ----------------
@ensure_csrf_cookie
def get_csrf(request):
    return JsonResponse({'detail': 'CSRF cookie set'})


# ---------------- Home ----------------
from auth_app.views.home import home

# ---------------- Passwordless Login ----------------
from auth_app.views.passwordless_login import passwordless_login_api, password_login_api

# ---------------- Signup / Verification ----------------
from auth_app.views.signup import signup_api
from auth_app.views.request_code import request_code_api as signup_request_code
from auth_app.views.verify_code import verify_code_api as verify_code

# ---------------- Social Login ----------------
from auth_app.views.social import social_login_api, social_login_callback

# ---------------- Profile ----------------
from auth_app.views.profile import send_profile_to_rabbitmq

# ---------------- Session ----------------
from auth_app.views.session import logout_api, session_status_api


# ---------------- Public API ----------------
__all__ = [
    "get_csrf",
    "home",
    "passwordless_login_api",
    "password_login_api",
    "signup_api",            # Creates user and sends verification
    "signup_request_code",   # Resend verification code
    "verify_code",           # Verify code and complete onboarding
    "social_login_api",
    "social_login_callback",
    "send_profile_to_rabbitmq",
    "session_status_api",
    "logout_api",
]
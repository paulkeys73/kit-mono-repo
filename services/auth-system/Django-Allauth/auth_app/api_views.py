from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie

# ---------------- CSRF ----------------
@ensure_csrf_cookie
def get_csrf(request):
    return JsonResponse({'detail': 'CSRF cookie set'})

# ---------------- Import Sub-Views ---------------
# These MUST be imported AFTER defining get_csrf
# and MUST be top-level so Django sees them

from auth_app.views.home import home
from auth_app.views.login import login_api
from auth_app.views.signup import signup_api, email_confirmed_view, resend_activation_email
from auth_app.views.social import social_login_api, social_login_callback
from auth_app.views.password import reset_password_api, reset_password_confirm_view
from auth_app.views.profile import send_profile_to_rabbitmq
from auth_app.views.session import  logout_api, session_status_view

__all__ = [
    "get_csrf",
    "home",
    "login_api",
    "signup_api",
    "email_confirmed_view",
    "resend_activation_email",
    "social_login_api",
    "social_login_callback",
    "reset_password_api",
    "reset_password_confirm_view",
    "send_profile_to_rabbitmq",
    "session_status_view",
    "logout_api",
]

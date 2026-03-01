# Django_Allauth: Django_Settings/urls.py

from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from django.conf import settings
from django.conf.urls.static import static

# ---------------- API Views ----------------
from auth_app import api_views as views
from auth_app.avatar import initials_avatar_svg

urlpatterns = [
    # ---------------- Admin ----------------
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),

    # ---------------- API ----------------
    path('', views.home, name='home'),
    path('csrf/', views.get_csrf, name='get_csrf'),

    # -------- Passwordless Auth / Signup --------
    path('api/signup/', views.signup_api, name='signup_api'),
    path('api/signup-request-code/', views.signup_request_code, name='signup_request_code'),
    path('api/request-code/', views.signup_request_code, name='request_code'),
    path('api/signup-request-code', views.signup_request_code),
    path('api/request-code', views.signup_request_code),
    path('api/verify-code/', views.verify_code, name='verify_code'),
    path('api/login/', views.password_login_api, name='password_login_api'),
    path('api/passwordless-login/', views.passwordless_login_api, name='passwordless_login'),

    # -------- Session --------
    path('api/session/', views.session_status_api, name='session_status_api'),
    path('api/logout/', views.logout_api, name='logout_api'),

    # -------- Social Login --------
    path('api/social-login/<str:provider>/', views.social_login_api, name='social_login_api'),
    path('api/social-login/google/callback/', views.social_login_callback, name='social_login_callback'),

    # -------- Profile --------
    path('api/profile/', views.send_profile_to_rabbitmq, name='profile'),

    # -------- Swagger --------
    path('swagger/', include('auth_app.swagger_urls')),

    # -------- Test Page --------
    path('test-auth/', lambda request: render(request, 'test_auth.html'), name='test_auth'),

    # -------- Initial Avatar --------
    path("avatar/<str:username>.svg", initials_avatar_svg, name="initials-avatar"),
]

# ---------------- Serve media files in development ----------------
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

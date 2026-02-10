# Django-Allauth/Django_Settings/urls.py

from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from django.conf import settings
from django.conf.urls.static import static

from auth_app import api_views as views

from auth_app.avatar import initials_avatar_svg
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,
)

urlpatterns = [
    # ---------------- Admin ----------------
    path('admin/', admin.site.urls),

    # ---------------- Allauth ----------------
    path('accounts/', include('allauth.urls')),

    # ---------------- API ----------------
    path('', views.home, name='home'),
    path('csrf/', views.get_csrf, name='get_csrf'),
    path('api/signup/', views.signup_api, name='signup_api'),
    path('verify-email/<str:key>/', views.email_confirmed_view, name='email_confirmed'),
    path('api/login/', views.login_api, name='login_api'),
    path('api/session/', views.session_status_view, name='session_status_api'),
    path('api/logout/', views.logout_api, name='logout_api'),
    path('api/reset-password/', views.reset_password_api, name='reset_password_api'),
    path('api/reset-password-confirm/', views.reset_password_confirm_view, name='reset_password_confirm_view'),
    path('api/resend-activation/', views.resend_activation_email, name='resend_activation'),
    path('api/social-login/<str:provider>/', views.social_login_api, name='social_login_api'),
    path('api/social-login/google/callback/', views.social_login_callback, name='social_login_callback'),
    path('api/profile/', views.send_profile_to_rabbitmq, name='profile'),

    # ---------------- Swager ----------------
    path('swagger/', include('auth_app.swagger_urls')),

    # ---------------- JWT ----------------
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),

    # ---------------- Test Page ----------------
    path('test-auth/', lambda request: render(request, 'test_auth.html'), name='test_auth'),

    # ---------------- Initial Avatar ----------------
    path("avatar/<str:username>.svg", initials_avatar_svg, name="initials-avatar"),
]

# ---------------- Serve media files in development ----------------
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

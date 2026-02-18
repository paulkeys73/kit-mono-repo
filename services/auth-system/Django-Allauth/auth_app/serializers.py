#E:\auth-system\Django-Allauth\auth_app\serializers.py

from rest_framework import serializers
from .models import CustomUser
from allauth.account.models import EmailAddress
from django.conf import settings


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    verified = serializers.SerializerMethodField()
    social = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id", "username", "first_name", "last_name", "full_name", "email",
            "phone", "bio", "location", "country", "address", "state", "city",
            "postal_code", "profile_image", "social", "avatar", "verified",
            "facebook_url", "x_url", "linkedin_url", "instagram_url",
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_avatar(self, obj):
        # If user uploaded a real image → use it
        if getattr(obj, "profile_image", None):
            try:
                return obj.profile_image.url
            except Exception:
                pass

        # Otherwise → use initials avatar SVG endpoint
        base_url = getattr(settings, "BASE_URL", "http://localhost:8034")
        return f"{base_url}/avatar/{obj.username}.svg"

    def get_verified(self, obj):
        try:
            email_record = EmailAddress.objects.get(user=obj, primary=True)
            return email_record.verified
        except EmailAddress.DoesNotExist:
            return False

    def get_social(self, obj):
        return {
            "facebook": obj.facebook_url or "",
            "x": obj.x_url or "",
            "linkedin": obj.linkedin_url or "",
            "instagram": obj.instagram_url or ""
        }

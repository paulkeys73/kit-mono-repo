from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import random
from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver
from auth_app.utils import generate_initials_avatar_svg
from allauth.account.models import EmailAddress

# ------------------------------
# DEFAULTS FOR USERS
# ------------------------------
USER_DEFAULTS = {
    "phone": "+1 22233344455",
    "bio": "Welcome to my profile!",
    "location": "Localhost",
    "address": "4 shalva gogidze street",
    "city": "Digomi",
    "state": "Tbilisi",
    "postal_code": "0102",
    "country": "Georgia",
    "facebook_url": "https://www.facebook.com/official.paulkeys",
    "x_url": "https://x.com/PaulKeys17",
    "linkedin_url": "https://www.linkedin.com/in/wordpress-developer-full-stack-dev/",
    "instagram_url": "https://www.instagram.com/paul_keys_music_dev",
}


# -------------------------------------------------
# CUSTOM USER MODEL
# -------------------------------------------------
class CustomUser(AbstractUser):
    # 🔒 Disable password requirement
    def set_password(self, raw_password):
        """
        Support both password and passwordless accounts.
        """
        if raw_password:
            super().set_password(raw_password)
        else:
            super().set_unusable_password()

    # Core fields
    phone = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    # Profile image
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)

    # Social links
    facebook_url = models.URLField(blank=True, null=True)
    x_url = models.URLField(blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)

    # Groups and permissions
    groups = models.ManyToManyField(Group, related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name='customuser_permissions_set', blank=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.username


# -------------------------------------------------
# EMAIL VERIFICATION MODEL
# -------------------------------------------------
class EmailVerification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="verifications")
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_code():
        return str(random.randint(100000, 999999))

    @classmethod
    def create_for_user(cls, user):
        return cls.objects.create(
            user=user,
            code=cls.generate_code(),
            expires_at=timezone.now() + timedelta(minutes=10)
        )

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.email} - {self.code}"


# -------------------------------------------------
# POST-SAVE SIGNAL TO AUTO-POPULATE USER FIELDS
# -------------------------------------------------
@receiver(post_save, sender=CustomUser)
def auto_populate_user(sender, instance, created, **kwargs):
    """
    Automatically fill in default values and generate avatar on user creation.
    """
    if not created:
        return

    updated = False

    # Apply defaults
    for field, value in USER_DEFAULTS.items():
        if not getattr(instance, field):
            setattr(instance, field, value)
            updated = True

    # Generate profile image if missing
    if not instance.profile_image:
        filename, buffer = generate_initials_avatar_svg(instance.full_name or instance.username)
        instance.profile_image.save(filename, ContentFile(buffer.getvalue()), save=False)
        updated = True

    if updated:
        instance.save()


# -------------------------------------------------
# POST-SAVE SIGNAL TO SYNC EMAILS (VERIFICATION CONTROLLED)
# -------------------------------------------------
@receiver(post_save, sender=CustomUser)
def sync_email_address(sender, instance, created, **kwargs):
    """
    Keep django-allauth EmailAddress in sync with CustomUser.
    Do NOT override verified flag if it already exists.
    """

    if not instance.email:
        return

    # Remove other emails for this user
    EmailAddress.objects.filter(user=instance).exclude(email=instance.email).delete()

    email_obj, email_created = EmailAddress.objects.get_or_create(
        user=instance,
        email=instance.email,
        defaults={
            "primary": True,
            "verified": False,  # Only applies if newly created
        }
    )

    # Ensure primary is correct
    if not email_obj.primary:
        email_obj.primary = True
        email_obj.save(update_fields=["primary"])




def mark_email_verified(user):
    try:
        email_obj = EmailAddress.objects.get(user=user, email=user.email)

        if not email_obj.verified:
            email_obj.verified = True
            email_obj.save(update_fields=["verified"])
            print(f"✅ Email verified for user {user.id}")

    except EmailAddress.DoesNotExist:
        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True
        )
        print(f"⚠️ EmailAddress missing, created and verified for user {user.id}")


        
        
        


@receiver(post_save, sender=EmailVerification)
def auto_verify_email(sender, instance, **kwargs):
    """
    Automatically mark email verified when a verification code is used.
    """
    if instance.is_used:
        mark_email_verified(instance.user)


        

from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models


class CustomUser(AbstractUser):
    # Core fields
    phone = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name="Phone number"
    )
    bio = models.TextField(
        blank=True, null=True,
        verbose_name="Biography"
    )
    location = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Location (City/State)"
    )
    address = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Street address"
    )
    city = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="City"
    )
    state = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="State/Province"
    )
    postal_code = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name="Postal code"
    )
    country = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Country"
    )

    # Profile image
    profile_image = models.ImageField(
        upload_to='profile_images/', blank=True, null=True,
        verbose_name="Profile image"
    )

    # Social links
    facebook_url = models.URLField(
        blank=True, null=True,
        verbose_name="Facebook profile URL"
    )
    x_url = models.URLField(
        blank=True, null=True,
        verbose_name="X (Twitter) profile URL"
    )
    linkedin_url = models.URLField(
        blank=True, null=True,
        verbose_name="LinkedIn profile URL"
    )
    instagram_url = models.URLField(
        blank=True, null=True,
        verbose_name="Instagram profile URL"
    )

    # Groups and permissions
    groups = models.ManyToManyField(
        Group,
        related_name='customuser_set',
        blank=True,
        help_text='Groups this user belongs to.',
        verbose_name='Groups'
    )

    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_permissions_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='User permissions'
    )

    @property
    def full_name(self):
        """Return first + last name as full name."""
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.username

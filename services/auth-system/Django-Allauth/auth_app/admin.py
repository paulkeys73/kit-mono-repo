from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress
from django.utils.html import format_html
from django.shortcuts import redirect
from django.urls import path

User = get_user_model()  # CustomUsers

# ---------------- Custom User Form with placeholders ----------------
class CustomUserChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'username': 'Enter username',
            'email': 'Enter email',
            'first_name': 'First name',
            'last_name': 'Last name',
            'phone': 'Phone number',
            'bio': 'Short biography',
            'address': 'Street address',
            'city': 'City',
            'state': 'State/Province',
            'postal_code': 'Postal code',
            'location': 'City/State',
            'country': 'Country',
            'facebook_url': 'https://facebook.com/username',
            'x_url': 'https://x.com/username',
            'linkedin_url': 'https://linkedin.com/in/username',
            'instagram_url': 'https://instagram.com/username',
        }
        for field, placeholder in placeholders.items():
            if field in self.fields:
                self.fields[field].widget.attrs.update({'placeholder': placeholder})

# --------------- Custom UserAdmin ---------------
class CustomUserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'is_verified',
        'is_staff', 'is_superuser', 'bio', 'phone', 'country',
        'address', 'city', 'state', 'postal_code',
        'facebook_url', 'x_url', 'linkedin_url', 'instagram_url'
    )
    # ... rest  code remains unchanged

    list_filter = ('is_staff', 'is_superuser', 'is_active', 'country')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'country')
    ordering = ('username',)

    def is_verified(self, obj):
        return EmailAddress.objects.filter(user=obj, verified=True).exists()
    is_verified.boolean = True
    is_verified.short_description = 'Verified'

    # Fieldsets
    fieldsets = (
        ('Login Credentials', {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'bio', 'profile_image')}),
        ('Address Details', {'fields': ('address', 'city', 'state', 'postal_code', 'location', 'country')}),
        ('Social Links', {'fields': ('facebook_url', 'x_url', 'linkedin_url', 'instagram_url')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'password1', 'password2',
                'first_name', 'last_name', 'phone', 'bio',
                'address', 'city', 'state', 'postal_code',
                'location', 'country', 'profile_image',
                'facebook_url', 'x_url', 'linkedin_url', 'instagram_url',
                'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'
            ),
        }),
    )

    readonly_fields = ('last_login', 'date_joined')

# ---------------- EmailAddressAdmin ----------------
try:
    admin.site.unregister(EmailAddress)
except admin.sites.NotRegistered:
    pass

@admin.register(EmailAddress)
class EmailAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_display', 'verified', 'primary', 'verify_action')
    search_fields = ('user__username', 'email')
    list_filter = ('verified', 'primary')
    actions = ['make_verified']

    def email_display(self, obj):
        return obj.email
    email_display.short_description = 'Email'
    email_display.admin_order_field = 'email'

    def make_verified(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} email(s) marked as verified.")
    make_verified.short_description = "Mark selected emails as verified"

    def verify_action(self, obj):
        if not obj.verified:
            return format_html(
                '<a class="button" href="{}">Verify</a>',
                f'{obj.id}/verify/'
            )
        return 'Already Verified'
    verify_action.short_description = 'Manual Verification'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:email_id>/verify/', self.admin_site.admin_view(self.verify_email), name='emailaddress-verify'),
        ]
        return custom_urls + urls

    def verify_email(self, request, email_id, *args, **kwargs):
        email_obj = self.get_object(request, email_id)
        if email_obj and not email_obj.verified:
            email_obj.verified = True
            email_obj.save()
            self.message_user(request, f"{email_obj.email} marked as verified!")
        return redirect(request.META.get('HTTP_REFERER', '/admin/'))

# ---------------- Register CustomUser ----------------
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

admin.site.register(User, CustomUserAdmin)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PasswordResetOTP, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "phone", "full_name", "is_staff", "is_active", "deletion_requested_at"]
    list_filter = ["is_staff", "is_active", ("deletion_requested_at", admin.EmptyFieldListFilter)]
    search_fields = ["email", "phone", "full_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "photo", "address", "latitude", "longitude")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        # Requested by the user in the app; nothing is deleted automatically.
        ("Account deletion", {"fields": ("deletion_requested_at", "deletion_reason")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "phone", "full_name", "password1", "password2")}),
    )


@admin.register(PasswordResetOTP)
class PasswordResetOTPAdmin(admin.ModelAdmin):
    list_display = ["user", "expires_at", "used_at", "created_at"]
    readonly_fields = ["otp_digest", "created_at"]

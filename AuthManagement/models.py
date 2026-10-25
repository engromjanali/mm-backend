import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

# A requested account deletion takes effect this long after the request; the
# user can cancel it until then.
ACCOUNT_DELETION_GRACE = timedelta(days=60)


class UserManager(BaseUserManager):
    def create_user(self, email, phone, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        if not phone:
            raise ValueError("A phone number is required.")

        user = self.model(
            email=self.normalize_email(email).lower(),
            phone=phone.strip(),
            full_name=full_name,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, phone, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self.create_user(email, phone, full_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True)
    photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    # The real membership in the selected season. It is null when mess-level
    # leadership grants access to a season the user never joined.
    current_membership = models.ForeignKey(
        'MessManagement.MessMemberShip', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    current_season = models.ForeignKey(
        'MessManagement.MessSeason', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    # Account deletion the user asked for; nothing is deleted automatically.
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    deletion_reason = models.TextField(blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone", "full_name"]

    def __str__(self):
        return self.email

    class Meta:
        db_table = 'users'

    @property
    def deletion_scheduled_for(self):
        """When the requested deletion takes effect, or None."""
        return self.deletion_requested_at + ACCOUNT_DELETION_GRACE if self.deletion_requested_at else None


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_otps")
    otp_digest = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'password_reset_otps'
        ordering = ["-created_at"]

    @staticmethod
    def digest(otp):
        return hmac.new(
            settings.SECRET_KEY.encode(), str(otp).encode(), hashlib.sha256
        ).hexdigest()

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"Password reset for {self.user.email}"


class PushDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_devices')
    token = models.CharField(max_length=512, unique=True)
    topics = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    season = models.ForeignKey('MessManagement.MessSeason', on_delete=models.SET_NULL, null=True)
    notice_id = models.PositiveBigIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-id']
        indexes = [models.Index(fields=['user', '-id'], name='notification_user_id_idx')]
        constraints = [models.UniqueConstraint(fields=['user', 'notice_id'], name='notification_user_notice_unique')]

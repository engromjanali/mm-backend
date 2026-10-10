import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import (
    REFRESH_TOKEN,
    create_access_token,
    create_refresh_token,
    resolve_token_user,
)
from .models import PasswordResetOTP
from .serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    RefreshTokenSerializer,
    SignInSerializer,
    SignUpSerializer,
    UserProfileSerializer,
)

User = get_user_model()


def testfunc(request):
    return HttpResponse("this is a test api")

def authentication_response(user, message):
    return {
        "message": message,
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "token_type": "Bearer",
        "expires_in": int(settings.JWT_ACCESS_TOKEN_LIFETIME.total_seconds()),
        "refresh_expires_in": int(settings.JWT_REFRESH_TOKEN_LIFETIME.total_seconds()),
        "user": UserProfileSerializer(user).data,
    }


class SignUpView(generics.CreateAPIView):
    serializer_class = SignUpSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            authentication_response(user, "Account created successfully."),
            status=status.HTTP_201_CREATED,
        )


class SignInView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response(authentication_response(user, "Signed in successfully."))


class RefreshTokenView(APIView):
    """
    POST /api/v1/auth/refresh-token

    Body: {"refresh_token": "..."}

    Swaps a valid refresh token for a fresh access token.  A new refresh
    token is issued alongside it, so an app in daily use never has to make
    the user sign in again.  Expired, tampered-with, or access tokens sent
    here are rejected with 401.
    """
    permission_classes = [permissions.AllowAny]
    # No authenticator: a client refreshing usually still carries its expired
    # access token in the Authorization header, and that must not fail the
    # request before the refresh token is even read.
    authentication_classes = []

    def get_authenticate_header(self, request):
        # Without this, DRF would render token failures raised inside the
        # view as 403 instead of 401, since there is no authenticator to
        # supply the WWW-Authenticate header.
        return "Bearer"

    def post(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, _ = resolve_token_user(
            serializer.validated_data["refresh_token"], REFRESH_TOKEN
        )
        return Response(authentication_response(user, "Token refreshed successfully."))


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sign_in_type = serializer.validated_data["type"]
        identifier = serializer.validated_data[sign_in_type]
        lookup = {f"{sign_in_type}__iexact": identifier}
        user = User.objects.filter(**lookup, is_active=True).first()

        # Use the same public response whether an account exists or not.
        if user:
            PasswordResetOTP.objects.filter(user=user, used_at__isnull=True).update(
                used_at=timezone.now()
            )
            otp = self._create_unique_otp(user)
            send_mail(
                subject="Your password reset code",
                message=(
                    f"Your password reset code is {otp}. "
                    f"It expires in {settings.PASSWORD_RESET_OTP_LIFETIME_MINUTES} minutes."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

        return Response(
            {"message": "If the email is registered, a reset code has been sent."}
        )

    @staticmethod
    def _create_unique_otp(user):
        while True:
            otp = f"{secrets.randbelow(1_000_000):06d}"
            digest = PasswordResetOTP.digest(otp)
            if not PasswordResetOTP.objects.filter(otp_digest=digest).exists():
                PasswordResetOTP.objects.create(
                    user=user,
                    otp_digest=digest,
                    expires_at=timezone.now()
                    + timedelta(minutes=settings.PASSWORD_RESET_OTP_LIFETIME_MINUTES),
                )
                return otp


class ChangePasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        digest = PasswordResetOTP.digest(serializer.validated_data["otp"])
        with transaction.atomic():
            reset = (
                PasswordResetOTP.objects.select_for_update()
                .select_related("user")
                .filter(otp_digest=digest)
                .first()
            )
            if not reset or not reset.is_valid:
                return Response(
                    {"otp": ["The reset code is invalid or has expired."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            reset.user.set_password(serializer.validated_data["password"])
            reset.user.save(update_fields=["password"])
            reset.used_at = timezone.now()
            reset.save(update_fields=["used_at"])

        return Response({"message": "Password changed successfully."})


class ProfileView(generics.RetrieveAPIView):
    """
    GET /api/v1/auth/profile

    Returns the signed-in user's profile.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UpdateProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "put", "patch", "options"]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        response.data = {
            "message": "Profile updated successfully.",
            "user": response.data,
        }
        return response


class AccountDeletionView(APIView):
    """
    POST   /api/v1/user/account/delete  {password, reason?}  request deletion
    DELETE /api/v1/user/account/delete                      keep the account (cancel)

    The account is scheduled for deletion ``ACCOUNT_DELETION_GRACE`` (60 days)
    after the request; until then the user can sign in and cancel. The primary
    manager of a mess must hand over the role first.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.deletion_requested_at:
            raise ValidationError({"detail": f"Your account is already scheduled for deletion on {_local_date(user.deletion_scheduled_for)}."})
        password = str(request.data.get("password") or "")
        if not password:
            raise ValidationError({"password": "Enter your password to confirm."})
        if not user.check_password(password):
            raise ValidationError({"password": "Password is incorrect."})
        managed = user.managed_messes.first()
        if managed:
            raise ValidationError({"detail": f"You're the manager of {managed.name}. Make another member the manager before deleting your account."})

        user.deletion_requested_at = timezone.now()
        user.deletion_reason = str(request.data.get("reason") or "").strip()[:1000]
        user.save(update_fields=["deletion_requested_at", "deletion_reason"])
        return Response({
            "message": f"Your account will be deleted on {_local_date(user.deletion_scheduled_for)}. Sign in before then to keep it.",
            "deletion_scheduled_for": user.deletion_scheduled_for,
        })

    def delete(self, request):
        user = request.user
        if not user.deletion_requested_at:
            raise ValidationError({"detail": "Your account isn't scheduled for deletion."})
        user.deletion_requested_at = None
        user.deletion_reason = ""
        user.save(update_fields=["deletion_requested_at", "deletion_reason"])
        return Response({"message": "Deletion cancelled. Your account stays."})


def _local_date(value):
    """A datetime as the messes' local date, e.g. `03-12-2026`."""
    return timezone.localtime(value, ZoneInfo(settings.MESS_TIME_ZONE)).strftime("%d-%m-%Y")

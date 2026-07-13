import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import create_access_token
from .models import PasswordResetOTP
from .serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
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
        "token_type": "Bearer",
        "expires_in": int(settings.JWT_ACCESS_TOKEN_LIFETIME.total_seconds()),
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

import re
from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PasswordResetOTP, User


class AuthenticationAPITests(APITestCase):
    password = "StrongPass!234"

    def create_user(self):
        return User.objects.create_user(
            email="person@example.com",
            phone="01700000000",
            full_name="Test Person",
            password=self.password,
        )

    def test_signup_accepts_example_field_names_and_returns_jwt(self):
        response = self.client.post(
            reverse("auth_management:sign-up"),
            {
                "full-name": "New Person",
                "email": "NEW@example.com",
                "Phone": "01800000000",
                "Password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["access_token"])
        self.assertEqual(response.data["user"]["email"], "new@example.com")
        self.assertTrue(User.objects.get(email="new@example.com").check_password(self.password))

    def test_signin_works_with_email_or_phone(self):
        self.create_user()
        for sign_in_type, identifier in (
            ("email", "person@example.com"),
            ("phone", "01700000000"),
        ):
            response = self.client.post(
                reverse("auth_management:sign-in"),
                {"type": sign_in_type, "email/phone": identifier, "password": self.password},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["token_type"], "Bearer")

    def test_signin_rejects_bad_credentials(self):
        self.create_user()
        response = self.client.post(
            reverse("auth_management:sign-in"),
            {"type": "email", "email": "person@example.com", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forgot_and_change_password_flow(self):
        user = self.create_user()
        response = self.client.post(
            reverse("auth_management:forget-password"),
            {"type": "email", "email": user.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        otp = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()

        response = self.client.post(
            reverse("auth_management:change-password"),
            {"otp": otp, "password": "AnotherStrong!234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password("AnotherStrong!234"))

        reused = self.client.post(
            reverse("auth_management:change-password"),
            {"otp": otp, "password": "ThirdStrong!234"},
            format="json",
        )
        self.assertEqual(reused.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forget_password_accepts_phone_type(self):
        user = self.create_user()
        response = self.client.post(
            reverse("auth_management:forget-password"),
            {"type": "phone", "phone": user.phone},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_forget_password_requires_matching_identifier(self):
        self.create_user()
        response = self.client.post(
            reverse("auth_management:forget-password"),
            {"type": "phone", "email": "person@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_otp_is_rejected(self):
        user = self.create_user()
        otp = "123456"
        PasswordResetOTP.objects.create(
            user=user,
            otp_digest=PasswordResetOTP.digest(otp),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        response = self.client.post(
            reverse("auth_management:change-password"),
            {"otp": otp, "password": "AnotherStrong!234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_requires_token_and_can_be_updated(self):
        self.create_user()
        sign_in = self.client.post(
            reverse("auth_management:sign-in"),
            {"type": "phone", "phone": "01700000000", "password": self.password},
            format="json",
        )
        token = sign_in.data["access_token"]

        unauthenticated = self.client.patch(
            reverse("auth_management:update-profile"), {"address": "Dhaka"}, format="json"
        )
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.patch(
            reverse("auth_management:update-profile"),
            {"full-name": "Updated Person", "address": "Dhaka", "let": "23.8103000", "long": "90.4125000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["full_name"], "Updated Person")
        self.assertEqual(response.data["user"]["lat"], "23.8103000")

    def test_password_update_invalidates_old_token(self):
        self.create_user()
        sign_in = self.client.post(
            reverse("auth_management:sign-in"),
            {"type": "email", "email": "person@example.com", "password": self.password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sign_in.data['access_token']}")
        changed = self.client.patch(
            reverse("auth_management:update-profile"),
            {"password": "AnotherStrong!234"},
            format="json",
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        old_token = self.client.get(reverse("auth_management:update-profile"))
        self.assertEqual(old_token.status_code, status.HTTP_401_UNAUTHORIZED)

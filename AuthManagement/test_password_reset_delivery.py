from smtplib import SMTPServerDisconnected
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase

from .models import PasswordResetOTP, User


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetDeliveryTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='reset@example.com', phone='01712345678', full_name='Reset User', password='StrongPass!234')
        self.url = reverse('auth_management:forgot-password')

    def request_reset(self, email=None):
        return self.client.post(self.url, {'type': 'email', 'email': email or self.user.email}, format='json')

    def test_success_and_unknown_account_have_same_public_response(self):
        response = self.request_reset()
        unknown = self.request_reset('unknown@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(PasswordResetOTP.objects.filter(user=self.user, used_at__isnull=True).count(), 1)

    def test_delivery_failure_restores_previous_code_without_leaking_details(self):
        previous = PasswordResetOTP.objects.create(user=self.user, otp_digest=PasswordResetOTP.digest('123456'), expires_at=timezone.now() + timedelta(minutes=10))
        with patch('AuthManagement.views.send_mail', side_effect=SMTPServerDisconnected('private SMTP credentials')):
            response = self.request_reset()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', str(response.data))
        previous.refresh_from_db()
        self.assertIsNone(previous.used_at)
        self.assertEqual(PasswordResetOTP.objects.filter(user=self.user).count(), 1)

    def test_connection_failure_does_not_reveal_account_existence(self):
        with patch('AuthManagement.views.get_connection', side_effect=SMTPServerDisconnected('private transport error')):
            known = self.request_reset()
            unknown = self.request_reset('unknown@example.com')
        self.assertEqual(known.status_code, 503)
        self.assertEqual(known.data, unknown.data)
        self.assertFalse(PasswordResetOTP.objects.exists())

    def test_zero_delivery_is_not_reported_as_success(self):
        with patch('AuthManagement.views.send_mail', return_value=0):
            response = self.request_reset()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(PasswordResetOTP.objects.exists())

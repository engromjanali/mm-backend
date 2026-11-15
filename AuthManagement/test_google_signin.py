from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from .google_auth import GoogleAuthUnavailable, verify_google_id_token
from .models import User


class GoogleSignInAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='google@example.com',
            phone='01700000001',
            full_name='Google User',
            password='StrongPass!234',
        )
        self.url = reverse('auth_management:google-sign-in')

    @patch('AuthManagement.views.verify_google_id_token')
    def test_existing_account_signs_in_and_returns_jwt(self, verify):
        verify.return_value = {'email': 'google@example.com', 'email_verified': True}
        response = self.client.post(self.url, {'id_token': 'token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['email'], 'google@example.com')
        self.assertTrue(response.data['access_token'])
        self.assertTrue(response.data['refresh_token'])
        verify.assert_called_once_with('token')

    @patch('AuthManagement.views.verify_google_id_token')
    def test_unknown_email_creates_account_and_signs_in(self, verify):
        verify.return_value = {
            'email': 'new@example.com',
            'email_verified': True,
            'sub': '109876543210987654321',
            'name': 'New Google User',
        }
        response = self.client.post(self.url, {'id_token': 'token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['email'], 'new@example.com')
        self.assertEqual(response.data['user']['full_name'], 'New Google User')
        self.assertTrue(response.data['access_token'])
        self.assertTrue(response.data['refresh_token'])

        user = User.objects.get(email='new@example.com')
        self.assertIsNone(user.phone)
        self.assertTrue(user.is_active)

    @patch('AuthManagement.views.verify_google_id_token')
    def test_created_account_uses_given_and_family_name(self, verify):
        verify.return_value = {
            'email': 'parts@example.com',
            'email_verified': True,
            'sub': 'sub-parts',
            'given_name': 'Parts',
            'family_name': 'Person',
        }
        response = self.client.post(self.url, {'id_token': 'token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['full_name'], 'Parts Person')

    @patch('AuthManagement.views.verify_google_id_token')
    def test_existing_account_is_not_modified(self, verify):
        verify.return_value = {'email': 'google@example.com', 'email_verified': True, 'name': 'Changed Name'}
        response = self.client.post(self.url, {'id_token': 'token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, 'Google User')

    @patch('AuthManagement.views.verify_google_id_token')
    def test_inactive_account_is_rejected(self, verify):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        verify.return_value = {'email': 'google@example.com', 'email_verified': True}
        response = self.client.post(self.url, {'id_token': 'token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('inactive', response.data['detail'])

    def test_google_user_can_set_password_from_profile(self):
        user = User.objects.create_user(
            email='nopass@example.com',
            phone=None,
            full_name='No Password',
            password=None,
        )
        self.assertFalse(user.has_usable_password())
        self.client.force_authenticate(user=user)

        response = self.client.patch(
            reverse('auth_management:update-profile'),
            {'password': 'StrongPass!234'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password('StrongPass!234'))

    def test_missing_token_is_rejected(self):
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('id_token', response.data)

    def test_token_alias_is_accepted(self):
        with patch('AuthManagement.views.verify_google_id_token') as verify:
            verify.return_value = {'email': 'google@example.com', 'email_verified': True}
            response = self.client.post(self.url, {'idToken': 'token'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class GoogleTokenVerificationTests(APITestCase):
    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=['client-123'])
    @patch('AuthManagement.google_auth.id_token.verify_oauth2_token')
    def test_accepts_verified_token_for_known_client(self, verify):
        verify.return_value = {'aud': 'client-123', 'email': 'User@Example.com', 'email_verified': True}
        claims = verify_google_id_token('token')
        self.assertEqual(claims['email'], 'user@example.com')

    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=['client-123'])
    @patch('AuthManagement.google_auth.id_token.verify_oauth2_token')
    def test_rejects_token_for_another_client(self, verify):
        verify.return_value = {'aud': 'other-client', 'email': 'user@example.com', 'email_verified': True}
        with self.assertRaises(ValidationError):
            verify_google_id_token('token')

    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=['client-123'])
    @patch('AuthManagement.google_auth.id_token.verify_oauth2_token')
    def test_rejects_unverified_email(self, verify):
        verify.return_value = {'aud': 'client-123', 'email': 'user@example.com', 'email_verified': False}
        with self.assertRaises(ValidationError):
            verify_google_id_token('token')

    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=[])
    def test_unconfigured_client_ids_are_unavailable(self):
        with self.assertRaises(GoogleAuthUnavailable):
            verify_google_id_token('token')

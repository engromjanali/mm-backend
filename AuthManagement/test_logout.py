from django.urls import reverse
from rest_framework.test import APITestCase

from .authentication import create_access_token
from .models import User


class LogoutAPITests(APITestCase):
    def test_authenticated_logout_returns_ok(self):
        user = User.objects.create_user(email='logout@example.com', phone='01712345678', full_name='Logout User', password='StrongPass!234')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(user)}')
        response = self.client.post(reverse('auth_management:logout'), format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'message': 'Logged out successfully.'})
        self.assertEqual(self.client.get(reverse('auth_management:logout')).status_code, 405)

    def test_logout_requires_authentication(self):
        response = self.client.post(reverse('auth_management:logout'), format='json')
        self.assertEqual(response.status_code, 401)

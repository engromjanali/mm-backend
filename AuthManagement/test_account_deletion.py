from datetime import timedelta

from rest_framework.test import APITestCase

from .models import User


class AccountDeletionAPITests(APITestCase):
    """Deleting an account only schedules it 60 days ahead; nothing is removed and it can be cancelled."""

    url = '/api/v1/user/account/delete'

    def setUp(self):
        self.user = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.client.force_authenticate(user=self.user)

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))

    def test_request_schedules_deletion_60_days_ahead_and_deletes_nothing(self):
        response = self.client.post(self.url, {'password': 'pass12345', 'reason': 'Moving out'}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.deletion_scheduled_for, self.user.deletion_requested_at + timedelta(days=60))
        self.assertEqual(self.user.deletion_reason, 'Moving out')
        self.assertIn('Your account will be deleted on', response.data['message'])
        self.assertTrue(User.objects.filter(pk=self.user.pk, is_active=True).exists())
        self.assertIsNotNone(self.client.get('/api/v1/auth/profile').data['deletion_scheduled_for'])
        self.assertRejected(self.client.post(self.url, {'password': 'pass12345'}, format='json'), 'already scheduled for deletion')

    def test_password_is_required_and_checked(self):
        self.assertRejected(self.client.post(self.url, {}, format='json'), 'Enter your password to confirm.')
        self.assertRejected(self.client.post(self.url, {'password': 'wrong'}, format='json'), 'Password is incorrect.')

    def test_manager_must_hand_over_first(self):
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July'}, format='json')
        self.assertRejected(
            self.client.post(self.url, {'password': 'pass12345'}, format='json'),
            "You're the manager of Green House. Make another member the manager before deleting your account.",
        )

    def test_cancel_keeps_the_account(self):
        self.assertRejected(self.client.delete(self.url), "Your account isn't scheduled for deletion.")
        self.client.post(self.url, {'password': 'pass12345'}, format='json')

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_requested_at)
        self.assertIsNone(self.client.get('/api/v1/auth/profile').data['deletion_scheduled_for'])

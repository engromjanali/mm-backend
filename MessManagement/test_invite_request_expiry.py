from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import Mess, MessMemberShip, MessMemberShipInvitation, MessMemberShipRequest
from .utils import expire_stale_invites_and_requests


class InviteAndRequestExpiryTests(APITestCase):
    """Invitations and join requests nobody answers within 7 days expire."""

    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.as_user(self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July'}, format='json')
        self.mess = Mess.objects.get()

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def invite_alice(self):
        self.as_user(self.manager)
        response = self.client.post('/api/v1/admin/invites', {'user_id': self.alice.id}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return MessMemberShipInvitation.objects.get(pk=response.data['id'])

    def request_as_alice(self):
        self.as_user(self.alice)
        response = self.client.post('/api/v1/user/join-requests', {'mess_id': self.mess.id}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return MessMemberShipRequest.objects.get(pk=response.data['id'])

    def age(self, model, pk, days):
        field = 'invited_at' if model is MessMemberShipInvitation else 'requested_at'
        model.objects.filter(pk=pk).update(**{field: timezone.now() - timedelta(days=days)})

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))

    # -- invitations ----------------------------------------------------------

    def test_invite_lists_its_expiry_and_stays_valid_for_7_days(self):
        invite = self.invite_alice()
        listed = self.client.get('/api/v1/admin/invites').data[0]
        self.assertEqual(listed['expires_at'], invite.invited_at + timedelta(days=7))

        self.age(MessMemberShipInvitation, invite.pk, 6)
        self.as_user(self.alice)
        response = self.client.post('/api/v1/user/invites/accept', {'invite_code': invite.invite_code}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_expired_invite_cannot_be_accepted_and_a_new_one_can_be_sent(self):
        invite = self.invite_alice()
        self.age(MessMemberShipInvitation, invite.pk, 8)

        self.as_user(self.alice)
        statuses = [i['status'] for i in self.client.get('/api/v1/user/membership/status').data['invites']]
        self.assertEqual(statuses, ['expired'])
        self.assertRejected(
            self.client.post('/api/v1/user/invites/accept', {'invite_code': invite.invite_code}, format='json'),
            'This invitation expired on',
        )
        self.assertFalse(MessMemberShip.objects.filter(user=self.alice).exists())

        fresh = self.invite_alice()
        self.assertNotEqual(fresh.pk, invite.pk)
        self.assertRejected(self.client.delete('/api/v1/admin/invites', {'invite_id': invite.pk}, format='json'), 'This invitation already expired on')

    # -- join requests --------------------------------------------------------

    def test_expired_join_request_cannot_be_approved_and_the_user_can_ask_again(self):
        join_request = self.request_as_alice()
        self.age(MessMemberShipRequest, join_request.pk, 8)

        self.as_user(self.manager)
        listed = self.client.get('/api/v1/admin/join-requests').data[0]
        self.assertEqual(listed['status'], 'expired')
        self.assertRejected(
            self.client.post('/api/v1/admin/join-requests/decision', {'request_id': join_request.pk, 'decision': 'accepted'}, format='json'),
            "Alice's join request expired on",
        )
        self.assertFalse(MessMemberShip.objects.filter(user=self.alice).exists())

        self.as_user(self.alice)
        self.assertRejected(self.client.delete(f'/api/v1/user/join-requests/{join_request.pk}'), 'This join request already expired on')
        self.request_as_alice()

    def test_join_request_within_7_days_can_be_approved(self):
        join_request = self.request_as_alice()
        self.age(MessMemberShipRequest, join_request.pk, 6)

        self.as_user(self.manager)
        response = self.client.post('/api/v1/admin/join-requests/decision', {'request_id': join_request.pk, 'decision': 'accepted'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    # -- nightly job ------------------------------------------------------------

    def test_listing_reports_expiry_without_writing_to_the_table(self):
        invite = self.invite_alice()
        self.age(MessMemberShipInvitation, invite.pk, 8)

        self.assertEqual(self.client.get('/api/v1/admin/invites').data[0]['status'], 'expired')
        invite.refresh_from_db()
        self.assertEqual(invite.status, 'pending')

    def test_nightly_job_saves_expired_only_on_stale_pending_rows(self):
        stale = self.invite_alice()
        self.age(MessMemberShipInvitation, stale.pk, 8)
        old_request = self.request_as_alice()
        self.age(MessMemberShipRequest, old_request.pk, 8)
        bob = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.as_user(self.manager)
        fresh = MessMemberShipInvitation.objects.get(pk=self.client.post('/api/v1/admin/invites', {'user_id': bob.id}, format='json').data['id'])

        self.assertEqual(expire_stale_invites_and_requests(), (1, 1))

        stale.refresh_from_db()
        old_request.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual((stale.status, old_request.status, fresh.status), ('expired', 'expired', 'pending'))

    def test_cron_endpoint_needs_the_secret(self):
        url = '/api/v1/cron/expire-invites-and-requests'
        with override_settings(CRON_SECRET=''):
            self.assertRejected(self.client.get(url, HTTP_AUTHORIZATION='Bearer x'), "CRON_SECRET isn't configured", 403)
        with override_settings(CRON_SECRET='s3cret'):
            self.assertRejected(self.client.get(url, HTTP_AUTHORIZATION='Bearer wrong'), 'Invalid cron secret.', 403)
            invite = self.invite_alice()
            self.age(MessMemberShipInvitation, invite.pk, 8)
            response = self.client.get(url, HTTP_AUTHORIZATION='Bearer s3cret')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['invites'], 1)
            invite.refresh_from_db()
            self.assertEqual(invite.status, 'expired')

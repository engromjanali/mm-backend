from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import Mess, MessMemberShip, MessMemberShipInvitation, MessSeason


class MembershipFlowTests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.bob = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def create_mess(self, user=None, name='Green House'):
        self.as_user(user or self.manager)
        return self.client.post('/api/v1/user/messes/create', {'name': name, 'season_name': 'July 2026', 'address': 'Mirpur'}, format='json')

    # -- create ---------------------------------------------------------------

    def test_create_mess_makes_creator_manager_with_first_season(self):
        response = self.create_mess()
        self.assertEqual(response.status_code, 201)
        mess = Mess.objects.get(name='Green House')
        self.assertEqual(mess.manager, self.manager)
        self.assertEqual(mess.active_season.name, 'July 2026')
        self.assertEqual(response.data['current']['role'], 'manager')

        profile = self.client.get('/api/v1/auth/profile')
        self.assertEqual(profile.data['active_mess_id'], mess.id)

    def test_cannot_create_second_mess_while_connected(self):
        self.create_mess()
        self.assertEqual(self.create_mess(name='Other').status_code, 400)

    # -- public list ----------------------------------------------------------

    def test_public_mess_list_needs_no_auth_and_paginates(self):
        self.create_mess()
        self.create_mess(user=self.alice, name='Blue House')
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/user/messes', {'per_page': 1, 'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['meta']['total'], 2)
        self.assertEqual(response.data['meta']['last_page'], 2)
        self.assertEqual(response.data['data'][0]['name'], 'Green House')

        searched = self.client.get('/api/v1/user/messes', {'search': 'blue'})
        self.assertEqual([m['name'] for m in searched.data['data']], ['Blue House'])

    # -- join request ---------------------------------------------------------

    def test_join_request_approved_by_manager(self):
        self.create_mess()
        mess = Mess.objects.get()

        self.as_user(self.alice)
        self.assertEqual(self.client.post('/api/v1/user/join-requests', {'mess_id': mess.id}, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/v1/user/join-requests', {'mess_id': mess.id}, format='json').status_code, 400)
        status = self.client.get('/api/v1/user/membership/status').data
        self.assertIsNone(status['current'])
        self.assertEqual(status['pending_requests'][0]['mess_id'], mess.id)

        # Members cannot see admin endpoints.
        self.assertEqual(self.client.get('/api/v1/admin/join-requests').status_code, 403)

        self.as_user(self.manager)
        requests = self.client.get('/api/v1/admin/join-requests').data
        self.assertEqual(requests[0]['user_email'], 'alice@test.com')
        decision = self.client.post('/api/v1/admin/join-requests/decision', {'request_id': requests[0]['id'], 'decision': 'accepted'}, format='json')
        self.assertEqual(decision.status_code, 200)

        self.as_user(self.alice)
        current = self.client.get('/api/v1/user/membership/status').data['current']
        self.assertEqual(current['mess_id'], mess.id)
        self.assertEqual(current['role'], 'member')

    # -- invite ---------------------------------------------------------------

    def test_invite_found_by_lookup_and_accepted_with_code(self):
        self.create_mess()
        lookup = self.client.get('/api/v1/admin/member-lookup', {'query': 'bob@test.com'})
        self.assertTrue(lookup.data['available'])
        invite = self.client.post('/api/v1/admin/invites', {'user_id': lookup.data['id']}, format='json')
        self.assertEqual(invite.status_code, 201)
        code = invite.data['invite_code']

        # Someone else cannot use Bob's invite.
        self.as_user(self.alice)
        self.assertEqual(self.client.post('/api/v1/user/invites/accept', {'invite_code': code}, format='json').status_code, 400)

        self.as_user(self.bob)
        self.assertEqual(self.client.get('/api/v1/user/membership/status').data['invites'][0]['invite_code'], code)
        accepted = self.client.post('/api/v1/user/invites/accept', {'invite_code': code.lower()}, format='json')
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data['current']['mess_name'], 'Green House')
        self.assertEqual(MessMemberShipInvitation.objects.get().status, 'accepted')

    def test_manager_can_revoke_invite(self):
        self.create_mess()
        invite = self.client.post('/api/v1/admin/invites', {'user_id': self.bob.id}, format='json').data
        self.assertEqual(self.client.delete('/api/v1/admin/invites', {'invite_id': invite['id']}, format='json').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/invites').data, [])

    # -- seasons --------------------------------------------------------------

    def test_new_season_carries_members_who_did_not_leave(self):
        self.create_mess()
        mess = Mess.objects.get()
        for user in (self.alice, self.bob):
            self.client.post('/api/v1/admin/invites', {'user_id': user.id}, format='json')
        for user in (self.alice, self.bob):
            self.as_user(user)
            code = self.client.get('/api/v1/user/membership/status').data['invites'][0]['invite_code']
            self.client.post('/api/v1/user/invites/accept', {'invite_code': code}, format='json')

        self.as_user(self.bob)
        self.assertEqual(self.client.post('/api/v1/user/membership/leave').status_code, 200)

        self.as_user(self.manager)
        old_season = mess.active_season
        response = self.client.post('/api/v1/admin/seasons', {'name': 'August 2026'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['members_carried'], 2)

        old_season.refresh_from_db()
        self.assertFalse(old_season.is_active)
        new_season = MessSeason.objects.get(is_active=True)
        self.assertEqual(
            set(MessMemberShip.objects.filter(season=new_season).values_list('user__email', flat=True)),
            {'manager@test.com', 'alice@test.com'},
        )
        # Old season memberships stay untouched.
        self.assertEqual(MessMemberShip.objects.filter(season=old_season).count(), 3)
        # Manager authority carries over without a stored per-season role.
        self.assertEqual(self.client.get('/api/v1/admin/members').status_code, 200)

    def test_manager_cannot_leave_without_handover(self):
        self.create_mess()
        self.assertEqual(self.client.post('/api/v1/user/membership/leave').status_code, 400)

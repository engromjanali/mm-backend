from django.utils import timezone
from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import Mess, MessMemberShip


class MemberManagementAPITests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.bob = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.as_user(self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July 2026'}, format='json')
        for user in (self.alice, self.bob):
            self.as_user(self.manager)
            invite = self.client.post('/api/v1/admin/invites', {'user_id': user.id}, format='json').data
            self.as_user(user)
            self.client.post('/api/v1/user/invites/accept', {'invite_code': invite['invite_code']}, format='json')
        self.manager_m, self.alice_m, self.bob_m = (MessMemberShip.objects.get(user=u) for u in (self.manager, self.alice, self.bob))
        self.as_user(self.manager)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def act(self, action, membership, method='post'):
        return getattr(self.client, method)(f'/api/v1/admin/members/{membership.id}/{action}')

    def mess(self):
        return Mess.objects.get(pk=self.manager_m.mess_id)

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))

    # -- disable / enable ----------------------------------------------------

    def test_disable_and_enable_a_member(self):
        response = self.act('disable', self.alice_m)
        self.assertEqual(response.status_code, 200, response.data)
        self.alice_m.refresh_from_db()
        self.assertEqual(self.alice_m.status, 'inactive')

        # Alice loses access; the manager still sees her with include_disabled.
        self.as_user(self.alice)
        self.assertRejected(self.client.get('/api/v1/user/mess'), 'You are not connected to an active mess.')
        self.as_user(self.manager)
        self.assertNotIn('Alice', [m['name'] for m in self.client.get('/api/v1/admin/members').data])
        listed = {m['name']: m['disabled'] for m in self.client.get('/api/v1/admin/members?include_disabled=true').data}
        self.assertEqual(listed, {'Alice': True, 'Bob': False, 'Manager Mia': False})

        self.assertRejected(self.act('disable', self.alice_m), 'Alice is already disabled.')
        self.assertEqual(self.act('enable', self.alice_m).status_code, 200)
        self.assertRejected(self.act('enable', self.alice_m), 'Alice is already active.')
        self.as_user(self.alice)
        self.assertEqual(self.client.get('/api/v1/user/mess').status_code, 200)

    def test_members_who_left_are_listed_only_on_request(self):
        self.bob_m.left_at = timezone.now()
        self.bob_m.status = 'inactive'
        self.bob_m.save()
        self.assertNotIn('Bob', [m['name'] for m in self.client.get('/api/v1/admin/members').data])
        listed = {m['name']: m['state'] for m in self.client.get('/api/v1/admin/members?include_left=true').data}
        self.assertEqual(listed, {'Alice': 'active', 'Bob': 'left', 'Manager Mia': 'active'})

    def test_disable_guards(self):
        self.assertRejected(self.act('disable', self.manager_m), "You can't disable yourself.")
        # The acting manager can disable members, but not the primary manager.
        self.act('acting-manager', self.bob_m)
        self.as_user(self.bob)
        self.assertRejected(self.act('disable', self.manager_m), "The primary manager can't be disabled.")
        self.assertEqual(self.act('disable', self.alice_m).status_code, 200)

    def test_disabling_the_acting_manager_removes_the_role(self):
        self.act('acting-manager', self.bob_m)
        self.act('disable', self.bob_m)
        self.assertIsNone(self.mess().acting_manager_id)

    def test_members_who_left_cant_be_disabled_or_enabled(self):
        self.as_user(self.alice)
        self.client.post('/api/v1/user/membership/leave')
        self.as_user(self.manager)
        self.assertRejected(self.act('disable', self.alice_m), 'Alice left the mess. Invite them again instead.')
        self.assertRejected(self.act('enable', self.alice_m), 'Alice left the mess. Invite them again instead.')

    def test_member_of_several_messes_can_be_enabled(self):
        self.act('disable', self.alice_m)
        self.as_user(self.alice)
        self.client.post('/api/v1/user/messes/create', {'name': 'Blue House', 'season_name': 'S1'}, format='json')
        self.as_user(self.manager)
        self.assertEqual(self.act('enable', self.alice_m).status_code, 200)
        # Enabling doesn't change which membership Alice is working in.
        self.as_user(self.alice)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['name'], 'Blue House')

    # -- acting manager ------------------------------------------------------

    def test_assign_replace_and_remove_acting_manager(self):
        response = self.act('acting-manager', self.alice_m)
        self.assertEqual((response.status_code, response.data['message']), (200, 'Alice is now the acting manager.'))
        self.assertRejected(self.act('acting-manager', self.alice_m), 'Alice is already the acting manager.')

        replaced = self.act('acting-manager', self.bob_m)
        self.assertIn('Alice is a regular member again.', replaced.data['message'])
        self.assertEqual(self.mess().acting_manager_id, self.bob.id)

        self.assertRejected(self.act('acting-manager', self.alice_m, 'delete'), "Alice isn't the acting manager.")
        self.assertEqual(self.act('acting-manager', self.bob_m, 'delete').status_code, 200)
        self.assertIsNone(self.mess().acting_manager_id)

    def test_acting_manager_needs_an_active_member(self):
        self.assertRejected(self.act('acting-manager', self.manager_m), "You're the primary manager already.")
        self.act('disable', self.alice_m)
        self.assertRejected(self.act('acting-manager', self.alice_m), "Alice isn't an active member. Enable them first.")

    # -- transfer ownership --------------------------------------------------

    def test_transfer_ownership(self):
        self.act('acting-manager', self.alice_m)
        response = self.act('transfer-ownership', self.alice_m)
        self.assertEqual(response.status_code, 200, response.data)
        mess = self.mess()
        self.assertEqual((mess.manager_id, mess.acting_manager_id), (self.alice.id, None))

        # The old manager is a regular member now and can't manage any more.
        self.assertRejected(self.act('transfer-ownership', self.alice_m), 'Only the manager or acting manager can do this.', 403)
        self.as_user(self.alice)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['my_role'], 'manager')

    def test_transfer_guards(self):
        self.assertRejected(self.act('transfer-ownership', self.manager_m), "You're already the primary manager.")
        self.act('disable', self.bob_m)
        self.assertRejected(self.act('transfer-ownership', self.bob_m), "Bob isn't an active member. Enable them first.")

    # -- permissions & scope -------------------------------------------------

    def test_only_the_primary_manager_changes_leadership(self):
        self.act('acting-manager', self.bob_m)
        self.as_user(self.bob)
        self.assertRejected(self.act('acting-manager', self.alice_m), 'Only the primary manager can change the mess leadership.', 403)
        self.assertRejected(self.act('transfer-ownership', self.alice_m), 'Only the primary manager can change the mess leadership.', 403)

    def test_members_cannot_manage(self):
        self.as_user(self.alice)
        for action in ('disable', 'enable', 'acting-manager', 'transfer-ownership'):
            self.assertEqual(self.act(action, self.bob_m).status_code, 403, action)
        self.assertEqual(self.client.get('/api/v1/admin/members').status_code, 403)

    def test_members_of_other_seasons_are_not_found(self):
        august = self.client.post('/api/v1/admin/seasons', {'name': 'August 2026'}, format='json').data['season']
        self.client.post(f"/api/v1/admin/seasons/{august['id']}/switch")
        # alice_m belongs to July; the manager now works in August.
        self.assertRejected(self.act('disable', self.alice_m), 'Member not found in the current season.', 404)
        self.assertRejected(self.act('transfer-ownership', self.alice_m), 'Member not found in the current season.', 404)

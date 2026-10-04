from datetime import date

from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import MessMemberShip, MessMemberShipRequest


class MultiMembershipAPITests(APITestCase):
    """A user can belong to several messes (one membership per season) and switch the current one."""

    def setUp(self):
        self.mia = User.objects.create_user(email='mia@test.com', phone='01711111111', full_name='Mia', password='pass12345')
        self.bob = User.objects.create_user(email='bob@test.com', phone='01722222222', full_name='Bob', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01733333333', full_name='Alice', password='pass12345')
        self.green = self.create_mess(self.mia, 'Green House')
        self.blue = self.create_mess(self.bob, 'Blue House')
        self.invite(self.mia, self.alice)
        self.invite(self.bob, self.alice)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def create_mess(self, user, name):
        self.as_user(user)
        response = self.client.post('/api/v1/user/messes/create', {'name': name, 'season_name': 'July 2026'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['current']['mess_id']

    def invite(self, manager, user):
        self.as_user(manager)
        code = self.client.post('/api/v1/admin/invites', {'user_id': user.id}, format='json').data['invite_code']
        self.as_user(user)
        response = self.client.post('/api/v1/user/invites/accept', {'invite_code': code}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def membership(self, user, mess_id):
        return MessMemberShip.objects.filter(user=user, mess_id=mess_id).order_by('-season__start_date', '-id').first()

    def switch(self, membership_id):
        return self.client.post('/api/v1/user/membership/switch', {'membership_id': membership_id}, format='json')

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))

    # -- joining several messes ----------------------------------------------

    def test_user_belongs_to_several_messes_and_the_last_joined_is_current(self):
        self.as_user(self.alice)
        data = self.client.get('/api/v1/user/membership/status').data
        self.assertEqual(data['current']['mess_name'], 'Blue House')
        listed = {m['mess_name']: (m['is_current'], m['can_switch'], m['status']) for m in data['memberships']}
        self.assertEqual(listed, {'Blue House': (True, True, 'active'), 'Green House': (False, True, 'active')})
        self.assertEqual([m['mess_name'] for m in data['history']], ['Green House'])

    def test_cannot_join_a_mess_twice(self):
        self.as_user(self.alice)
        self.assertRejected(self.client.post('/api/v1/user/join-requests', {'mess_id': self.green}, format='json'), "You're already a member of Green House.")
        self.as_user(self.mia)
        self.assertRejected(self.client.post('/api/v1/admin/invites', {'user_id': self.alice.id}, format='json'), 'Alice is already a member of July 2026.')
        lookup = self.client.get('/api/v1/admin/member-lookup', {'query': 'alice@test.com'}).data
        self.assertFalse(lookup['available'])

    def test_join_request_while_in_another_mess(self):
        self.as_user(self.mia)
        response = self.client.post('/api/v1/user/join-requests', {'mess_id': self.blue}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.as_user(self.bob)
        decision = self.client.post('/api/v1/admin/join-requests/decision', {'request_id': response.data['id'], 'decision': 'accepted'}, format='json')
        self.assertEqual(decision.status_code, 200, decision.data)
        # Approval adds the membership but doesn't move Mia away from her own mess.
        self.as_user(self.mia)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['name'], 'Green House')
        self.assertTrue(self.membership(self.mia, self.blue))

    def test_accepting_an_invite_keeps_requests_to_other_messes(self):
        carol = User.objects.create_user(email='carol@test.com', phone='01744444444', full_name='Carol', password='pass12345')
        self.as_user(carol)
        self.client.post('/api/v1/user/join-requests', {'mess_id': self.blue}, format='json')
        self.invite(self.mia, carol)
        self.assertTrue(MessMemberShipRequest.objects.filter(user=carol, mess_id=self.blue, status='pending').exists())

    # -- switching -----------------------------------------------------------

    def test_switch_changes_what_every_screen_shows(self):
        self.as_user(self.alice)
        green = self.membership(self.alice, self.green)
        response = self.switch(green.id)
        self.assertEqual((response.status_code, response.data['message']), (200, 'Switched to Green House (July 2026).'))
        self.assertEqual(self.client.get('/api/v1/user/mess').data['name'], 'Green House')
        self.assertEqual(User.objects.get(pk=self.alice.pk).current_membership_id, green.id)

        # Notices follow the current membership too.
        self.as_user(self.mia)
        self.client.post('/api/v1/admin/notices', {'title': 'Green only', 'description': 'x'}, format='json')
        self.as_user(self.alice)
        self.assertEqual([n['title'] for n in self.client.get('/api/v1/user/notices').data['data']], ['Green only'])
        self.switch(self.membership(self.alice, self.blue).id)
        self.assertEqual(self.client.get('/api/v1/user/notices').data['data'], [])

    def test_manager_tools_follow_the_current_membership(self):
        # Mia manages Green; as a plain member of Blue she can't use admin endpoints there.
        self.invite(self.bob, self.mia)
        self.as_user(self.mia)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['my_role'], 'member')
        self.assertEqual(self.client.get('/api/v1/admin/members').status_code, 403)
        self.switch(self.membership(self.mia, self.green).id)
        self.assertEqual(self.client.get('/api/v1/admin/members').status_code, 200)

    def test_switch_to_an_older_season_which_stays_editable(self):
        self.as_user(self.mia)
        old = self.membership(self.mia, self.green)
        august = self.client.post('/api/v1/admin/seasons', {'name': 'August 2026'}, format='json').data['season']
        # The manager switches to the new season…
        self.client.post(f"/api/v1/admin/seasons/{august['id']}/switch")
        self.assertEqual(self.client.get('/api/v1/user/mess').data['season']['name'], 'August 2026')
        # …and the old season can still be opened and edited.
        self.assertEqual(self.switch(old.id).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['season']['name'], 'July 2026')
        notice = self.client.post('/api/v1/admin/notices', {'title': 'Old season fix', 'description': 'x'}, format='json')
        self.assertEqual(notice.status_code, 201, notice.data)

    def test_new_season_keeps_members_in_their_season_until_they_switch(self):
        self.as_user(self.alice)
        self.switch(self.membership(self.alice, self.green).id)
        self.as_user(self.mia)
        self.client.post('/api/v1/admin/seasons', {'name': 'August 2026'}, format='json')
        self.as_user(self.alice)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['season']['name'], 'July 2026')
        self.switch(self.membership(self.alice, self.green).id)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['season']['name'], 'August 2026')

    def test_switch_refusals(self):
        self.as_user(self.alice)
        green = self.membership(self.alice, self.green)
        self.assertRejected(self.switch('abc'), 'membership_id must be a number.')
        self.assertRejected(self.switch(self.membership(self.mia, self.green).id), 'Membership not found.', 404)

        self.as_user(self.mia)
        self.client.post(f'/api/v1/admin/members/{green.id}/disable')
        self.as_user(self.alice)
        self.assertRejected(self.switch(green.id), 'Your membership in Green House (July 2026) was disabled by its manager.')

        blue = self.membership(self.alice, self.blue)
        self.switch(blue.id)
        self.client.post('/api/v1/user/membership/leave')
        self.assertRejected(self.switch(blue.id), "You left Blue House (July 2026), so it can't be your current membership.")

    def test_leaving_falls_back_to_another_membership(self):
        self.as_user(self.alice)
        self.assertEqual(self.client.get('/api/v1/user/mess').data['name'], 'Blue House')
        self.client.post('/api/v1/user/membership/leave')
        self.assertEqual(self.client.get('/api/v1/user/mess').data['name'], 'Green House')
        self.client.post('/api/v1/user/membership/leave')
        self.assertRejected(self.client.get('/api/v1/user/mess'), 'You are not connected to an active mess.')

    def test_manager_cannot_leave_their_mess(self):
        self.as_user(self.mia)
        self.assertRejected(self.client.post('/api/v1/user/membership/leave'), 'Transfer the manager role before leaving the mess.')

    # -- history ---------------------------------------------------------------

    def test_status_and_manager_lists_keep_full_history(self):
        carol = User.objects.create_user(email='carol@test.com', phone='01744444444', full_name='Carol', password='pass12345')
        self.as_user(carol)
        request_id = self.client.post('/api/v1/user/join-requests', {'mess_id': self.green}, format='json').data['id']
        self.client.delete(f'/api/v1/user/join-requests/{request_id}')
        self.client.post('/api/v1/user/join-requests', {'mess_id': self.blue}, format='json')
        self.as_user(self.mia)
        code = self.client.post('/api/v1/admin/invites', {'user_id': carol.id}, format='json').data['invite_code']
        self.as_user(carol)
        self.client.post('/api/v1/user/invites/decline', {'invite_code': code}, format='json')

        data = self.client.get('/api/v1/user/membership/status').data
        self.assertEqual(sorted((r['mess_name'], r['status']) for r in data['join_requests']), [('Blue House', 'pending'), ('Green House', 'cancelled')])
        self.assertEqual([r['mess_name'] for r in data['pending_requests']], ['Blue House'])
        self.assertEqual([(i['mess_name'], i['status'], i['invited_by']) for i in data['invites']], [('Green House', 'declined', 'Mia')])

        self.as_user(self.mia)
        statuses = {(i['user_name'], i['status']) for i in self.client.get('/api/v1/admin/invites').data}
        self.assertIn(('Carol', 'declined'), statuses)
        self.assertIn(('Alice', 'accepted'), statuses)
        self.assertEqual([(r['user_name'], r['status']) for r in self.client.get('/api/v1/admin/join-requests').data], [('Carol', 'cancelled')])

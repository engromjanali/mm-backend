from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import MessMemberShip, Notices


class NoticeAPITests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.client.force_authenticate(user=self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July 2026'}, format='json')
        invite = self.client.post('/api/v1/admin/invites', {'user_id': self.alice.id}, format='json').data
        self.client.force_authenticate(user=self.alice)
        self.client.post('/api/v1/user/invites/accept', {'invite_code': invite['invite_code']}, format='json')
        self.client.force_authenticate(user=self.manager)

    def publish(self, title='Water off', description='No water 2–4 pm.', **extra):
        return self.client.post('/api/v1/admin/notices', {'title': title, 'description': description, **extra}, format='json')

    def pin(self, notice_id, pinned=True):
        return self.client.post(f'/api/v1/admin/notices/{notice_id}/pin', {'pinned': pinned}, format='json')

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))

    # -- read ----------------------------------------------------------------

    def test_members_and_manager_read_pinned_first_then_newest(self):
        first = self.publish('First').data['id']
        second = self.publish('Second').data['id']
        self.pin(first)

        for user in (self.manager, self.alice):
            self.client.force_authenticate(user=user)
            data = self.client.get('/api/v1/user/notices').data['data']
            self.assertEqual([n['id'] for n in data], [first, second])
            self.assertEqual((data[0]['pinned'], data[0]['description']), (True, 'No water 2–4 pm.'))

    def test_read_requires_an_active_mess(self):
        loner = User.objects.create_user(email='loner@test.com', phone='01744444444', full_name='Loner', password='pass12345')
        self.client.force_authenticate(user=loner)
        self.assertRejected(self.client.get('/api/v1/user/notices'), 'You are not connected to an active mess.')
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/v1/user/notices').status_code, (401, 403))

    def test_new_season_starts_with_an_empty_board(self):
        old_id = self.publish('Old season', pinned=True).data['id']
        august = self.client.post('/api/v1/admin/seasons', {'name': 'August 2026'}, format='json').data['season']
        self.client.post(f"/api/v1/admin/seasons/{august['id']}/switch")

        self.assertEqual(self.client.get('/api/v1/user/notices').data['data'], [])
        self.assertRejected(self.pin(old_id, False), 'Notice not found in the current season', 404)
        self.assertRejected(self.client.delete(f'/api/v1/admin/notices/{old_id}'), 'Notice not found in the current season', 404)

        # The new season has its own pinned slot; the old notice stays in its season.
        new_id = self.publish('New season', pinned=True).data['id']
        self.client.force_authenticate(user=self.alice)
        alice_august = MessMemberShip.objects.get(user=self.alice, season_id=august['id'])
        self.client.post('/api/v1/user/membership/switch', {'membership_id': alice_august.id}, format='json')
        self.assertEqual([n['id'] for n in self.client.get('/api/v1/user/notices').data['data']], [new_id])
        self.assertTrue(Notices.objects.get(id=old_id).is_pinned)
        self.assertEqual(Notices.objects.get(id=new_id).season.name, 'August 2026')

    def test_notices_of_another_mess_are_hidden(self):
        bob = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.client.force_authenticate(user=bob)
        self.client.post('/api/v1/user/messes/create', {'name': 'Blue House', 'season_name': 'S1'}, format='json')
        other_id = self.publish('Other mess').data['id']

        self.client.force_authenticate(user=self.manager)
        self.assertEqual(self.client.get('/api/v1/user/notices').data['data'], [])
        self.assertRejected(self.client.patch(f'/api/v1/admin/notices/{other_id}', {'title': 'x'}, format='json'), 'Notice not found in the current season', 404)
        self.assertRejected(self.pin(other_id), 'Notice not found in the current season', 404)
        self.assertRejected(self.client.delete(f'/api/v1/admin/notices/{other_id}'), 'Notice not found in the current season', 404)

    # -- write access --------------------------------------------------------

    def test_members_cannot_manage_notices(self):
        notice_id = self.publish().data['id']
        self.client.force_authenticate(user=self.alice)
        self.assertEqual(self.publish().status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/admin/notices/{notice_id}', {'title': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.pin(notice_id).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/v1/admin/notices/{notice_id}').status_code, 403)

    # -- publish -------------------------------------------------------------

    def test_publish_trims_and_can_pin(self):
        response = self.publish('  Rent due  ', '  Pay by the 5th.  ', pinned=True)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data['title'], response.data['description'], response.data['pinned']), ('Rent due', 'Pay by the 5th.', True))

    def test_publish_validation(self):
        self.assertRejected(self.publish('   '), "Title can't be empty.")
        self.assertRejected(self.publish(description=''), "Description can't be empty.")
        self.assertRejected(self.publish('x' * 201), "Title can't be longer than 200 characters.")
        self.assertRejected(self.publish(description='x' * 2001), "Description can't be longer than 2000 characters.")
        self.assertRejected(self.client.post('/api/v1/admin/notices', {'description': 'd'}, format='json'), 'Title is required.')
        self.assertRejected(self.publish(pinned='maybe'), 'pinned must be true or false.')
        self.assertEqual(Notices.objects.count(), 0)

    # -- edit ----------------------------------------------------------------

    def test_edit_changes_only_sent_fields(self):
        notice_id = self.publish().data['id']
        response = self.client.patch(f'/api/v1/admin/notices/{notice_id}', {'title': 'Water back'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['title'], response.data['description']), ('Water back', 'No water 2–4 pm.'))

    def test_edit_validation(self):
        notice_id = self.publish().data['id']
        patch = lambda body: self.client.patch(f'/api/v1/admin/notices/{notice_id}', body, format='json')
        self.assertRejected(patch({}), 'Send a title or description to update.')
        self.assertRejected(patch({'title': ''}), "Title can't be empty.")
        self.assertRejected(patch({'description': 'x' * 2001}), "Description can't be longer than 2000 characters.")
        self.assertRejected(self.client.patch('/api/v1/admin/notices/999999', {'title': 'x'}, format='json'), 'Notice not found in the current season', 404)

    # -- pin -----------------------------------------------------------------

    def test_pinning_one_unpins_the_other(self):
        first = self.publish('First', pinned=True).data['id']
        second = self.publish('Second').data['id']
        self.assertEqual(self.pin(second).data['pinned'], True)
        self.assertEqual(list(Notices.objects.filter(is_pinned=True).values_list('id', flat=True)), [second])
        self.assertFalse(Notices.objects.get(id=first).is_pinned)

        self.assertEqual(self.pin(second, False).data['pinned'], False)
        self.assertFalse(Notices.objects.filter(is_pinned=True).exists())

    def test_publishing_pinned_replaces_the_pinned_notice(self):
        self.publish('Old', pinned=True)
        new_id = self.publish('New', pinned=True).data['id']
        self.assertEqual(list(Notices.objects.filter(is_pinned=True).values_list('id', flat=True)), [new_id])

    def test_pin_validation(self):
        notice_id = self.publish().data['id']
        self.assertRejected(self.client.post(f'/api/v1/admin/notices/{notice_id}/pin', {}, format='json'), 'pinned is required')
        self.assertRejected(self.pin(notice_id, 'yes please'), 'pinned must be true or false.')
        self.assertRejected(self.pin(999999), 'Notice not found in the current season', 404)

    # -- delete --------------------------------------------------------------

    def test_delete(self):
        notice_id = self.publish().data['id']
        self.assertEqual(self.client.delete(f'/api/v1/admin/notices/{notice_id}').status_code, 200)
        self.assertRejected(self.client.delete(f'/api/v1/admin/notices/{notice_id}'), 'Notice not found in the current season', 404)

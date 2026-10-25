from datetime import date
from unittest.mock import patch

from rest_framework.test import APITestCase

from AuthManagement.models import Notification, User
from AuthManagement.notifications import save_notice_notifications
from MessManagement.models import Mess, MessMemberShip, MessSeason, Notices


class NotificationInboxTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='inbox@test.com', phone='01711111111', full_name='Inbox', password='pass12345')
        self.other = User.objects.create_user(email='other@test.com', phone='01711111112', full_name='Other', password='pass12345')
        self.mess = Mess.objects.create(name='Inbox mess', manager=self.user)
        self.season = MessSeason.objects.create(mess=self.mess, name='First', start_date=date.today())
        MessMemberShip.objects.create(user=self.user, mess=self.mess, season=self.season)
        self.user.current_season = self.season
        self.user.save()
        self.notice = Notices.objects.create(mess=self.mess, title='Dinner', content='Dinner at eight')
        save_notice_notifications(self.notice, self.season)
        self.item = Notification.objects.get(user=self.user)
        self.client.force_authenticate(self.user)

    def open(self):
        return self.client.post(f'/api/v1/user/notifications/{self.item.id}/open')

    def test_persists_once_and_opens_current_season(self):
        save_notice_notifications(self.notice, self.season)
        self.assertEqual(Notification.objects.count(), 1)
        from AuthManagement.push import notice_notification_content
        content = notice_notification_content(self.notice.title)
        self.assertEqual(self.item.title, content['title'])
        self.assertEqual(self.item.description, content['body'])
        self.assertNotEqual(self.item.description, self.notice.content)
        response = self.open()
        self.assertEqual(response.data['status'], 'ready')
        self.assertEqual(response.data['route'], f'/notices/{self.notice.id}')
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.read_at)

    def test_other_account_cannot_list_or_open(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/v1/user/notifications').data['data'], [])
        self.assertEqual(self.open().status_code, 404)

    def test_requires_season_change_and_keeps_snapshot(self):
        second = MessSeason.objects.create(mess=self.mess, name='Second', start_date=date.today())
        self.user.current_membership = None
        self.user.current_season = second
        self.user.save()
        response = self.open()
        self.assertEqual(response.data['status'], 'change_season')
        self.assertNotIn('route', response.data)
        self.assertEqual(response.data['title'], 'New Notice')
        self.assertEqual(response.data['description'], 'Dinner')

    def test_disabled_season_and_deleted_destination_are_unavailable(self):
        self.notice.delete()
        self.assertEqual(self.open().data['status'], 'unavailable')
        self.season.is_disabled = True
        self.season.save()
        self.assertEqual(self.open().data['status'], 'unavailable')

    def test_publish_saves_even_when_push_fails(self):
        with patch('AuthManagement.push.firebase_messaging', side_effect=RuntimeError('offline')):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post('/api/v1/admin/notices', {'title': 'New', 'description': 'Saved'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Notification.objects.filter(user=self.user, title='New Notice', description='New').exists())

    def test_list_is_paginated(self):
        Notification.objects.bulk_create([Notification(user=self.user, season=self.season, notice_id=1000+i, title='Title', description='Body') for i in range(35)])
        response = self.client.get('/api/v1/user/notifications')
        self.assertEqual(len(response.data['data']), 30)
        next_page = self.client.get('/api/v1/user/notifications', {'before': response.data['next']})
        self.assertEqual(len(next_page.data['data']), 6)

    def test_unread_indicator_is_account_scoped_and_clears_when_read(self):
        self.assertTrue(self.client.get('/api/v1/user/notifications', {'unread_only': 'true'}).data['has_unread'])
        self.client.force_authenticate(self.other)
        self.assertFalse(self.client.get('/api/v1/user/notifications', {'unread_only': 'true'}).data['has_unread'])
        self.client.force_authenticate(self.user)
        self.open()
        self.assertFalse(self.client.get('/api/v1/user/notifications', {'unread_only': 'true'}).data['has_unread'])

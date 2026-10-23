from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from AuthManagement.models import PushDevice, User
from AuthManagement.push import eligible_topics, mess_topic, send_notice_notification, season_topic
from MessManagement.models import Mess, MessMemberShip, MessSeason


class NoticePushTests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@push.test', phone='01711111111', full_name='Manager', password='pass12345')
        self.mess = Mess.objects.create(name='Mess', manager=self.manager)
        self.season = MessSeason.objects.create(mess=self.mess, name='Current', start_date=date.today())
        self.topic = season_topic(self.season.id)
        self.mess_topic = mess_topic(self.mess.id)
        self.manager.current_season = self.season
        self.manager.save(update_fields=['current_season'])
        self.client.force_authenticate(self.manager)
        self.messaging = MagicMock()
        self.messaging.subscribe_to_topic.return_value.failure_count = 0
        self.messaging.unsubscribe_from_topic.return_value.failure_count = 0
        self.patcher = patch('AuthManagement.push.firebase_messaging', return_value=self.messaging)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def member(self, name, status='active', **extra):
        user = User.objects.create_user(email=f'{name}@push.test', phone=f'017{User.objects.count():08d}', full_name=name, password='pass12345')
        MessMemberShip.objects.create(user=user, mess=self.mess, season=self.season, status=status, **extra)
        user.current_season = self.season
        user.save(update_fields=['current_season'])
        return user

    def test_only_usable_memberships_have_topics(self):
        from django.utils import timezone
        active = self.member('active')
        inactive = self.member('inactive', 'inactive')
        left = self.member('left', 'left')
        departed = self.member('departed', left_at=timezone.now())
        self.assertEqual(eligible_topics(active.id), {self.topic, self.mess_topic})
        for user in (inactive, left, departed):
            self.assertEqual(eligible_topics(user.id), set())
        self.season.is_disabled = True
        self.season.save()
        self.assertEqual(eligible_topics(active.id), set())

    def test_subscription_uses_server_membership_not_supplied_topic(self):
        user = self.member('active')
        self.client.force_authenticate(user)
        response = self.client.post('/api/v1/auth/push-device', {'token': 'device', 'topics': ['topic_seasonId_9999']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data['topics']), {self.topic, self.mess_topic})
        self.messaging.subscribe_to_topic.assert_any_call(['device'], self.topic)
        self.messaging.subscribe_to_topic.assert_any_call(['device'], self.mess_topic)

    def test_shared_device_removes_previous_account_topics(self):
        previous = self.member('previous')
        PushDevice.objects.create(user=previous, token='shared', topics=[self.topic])
        self.client.post('/api/v1/auth/push-device', {'token': 'shared'}, format='json')
        self.messaging.unsubscribe_from_topic.assert_called_once_with(['shared'], self.topic)
        device = PushDevice.objects.get(token='shared')
        self.assertEqual(device.user_id, self.manager.id)
        self.assertEqual(device.topics, [])

    def test_removes_disabled_and_left_devices_before_sending(self):
        active = self.member('active')
        inactive = self.member('inactive', 'inactive')
        left = self.member('left', 'left')
        for user in (active, inactive, left):
            PushDevice.objects.create(user=user, token=str(user.id), topics=[self.topic])
        send_notice_notification(12, self.season.id, 'Ajke meal hoy nai')
        self.assertEqual(self.messaging.unsubscribe_from_topic.call_count, 2)
        for user in (inactive, left):
            self.assertEqual(PushDevice.objects.get(user=user).topics, [])
        self.messaging.Notification.assert_called_once_with(title='New Notice', body='Ajke meal hoy nai')
        self.assertEqual(self.messaging.Message.call_args.kwargs['topic'], self.topic)
        self.assertEqual(self.messaging.Message.call_args.kwargs['data']['season_id'], str(self.season.id))
        self.messaging.send.assert_called_once()

    def test_active_members_receive_even_when_registered_without_topic(self):
        user = self.member('active')
        PushDevice.objects.create(user=user, token='device')
        send_notice_notification(12, self.season.id, 'Notice')
        self.messaging.subscribe_to_topic.assert_any_call(['device'], self.topic)
        self.messaging.subscribe_to_topic.assert_any_call(['device'], self.mess_topic)
        self.messaging.send.assert_called_once()

    def test_failed_removal_prevents_sending(self):
        user = self.member('left', 'left')
        PushDevice.objects.create(user=user, token='device', topics=[self.topic])
        self.messaging.unsubscribe_from_topic.return_value.failure_count = 1
        self.messaging.unsubscribe_from_topic.return_value.errors = [MagicMock(reason='internal-error')]
        send_notice_notification(12, self.season.id, 'Notice')
        self.messaging.send.assert_not_called()

    def test_disabled_season_is_not_notified(self):
        self.season.is_disabled = True
        self.season.save()
        send_notice_notification(12, self.season.id, 'Notice')
        self.messaging.send.assert_not_called()

    def test_creation_sends_once_after_commit_but_edit_does_not(self):
        with patch('MessManagement.notice_views.send_notice_notification') as send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post('/api/v1/admin/notices', {'title': 'Meals', 'description': 'No meals today'}, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                send.assert_not_called()
            send.assert_called_once_with(response.data['id'], self.season.id, 'Meals')
            self.client.patch(f"/api/v1/admin/notices/{response.data['id']}", {'description': 'Updated'}, format='json')
            self.assertEqual(send.call_count, 1)

    def test_unregister_is_scoped_to_device_owner(self):
        user = self.member('active')
        PushDevice.objects.create(user=user, token='device', topics=[self.topic])
        self.client.delete('/api/v1/auth/push-device', {'token': 'device'}, format='json')
        self.assertTrue(PushDevice.objects.filter(token='device').exists())
        self.client.force_authenticate(user)
        self.client.delete('/api/v1/auth/push-device', {'token': 'device'}, format='json')
        self.assertFalse(PushDevice.objects.filter(token='device').exists())

    def test_stale_unregistered_token_is_removed_without_blocking_delivery(self):
        user = self.member('left', 'left')
        PushDevice.objects.create(user=user, token='expired', topics=[self.topic])
        self.messaging.unsubscribe_from_topic.return_value.failure_count = 1
        self.messaging.unsubscribe_from_topic.return_value.errors = [MagicMock(reason='registration-token-not-registered')]
        send_notice_notification(12, self.season.id, 'Notice')
        self.assertFalse(PushDevice.objects.filter(token='expired').exists())
        self.messaging.send.assert_called_once()

    def test_other_season_subscriptions_are_removed(self):
        user = self.member('active')
        other_topic = season_topic(self.season.id + 1)
        device = PushDevice.objects.create(user=user, token='device', topics=[other_topic])
        send_notice_notification(12, self.season.id, 'Notice')
        device.refresh_from_db()
        self.assertEqual(set(device.topics), {self.topic, self.mess_topic})
        self.messaging.unsubscribe_from_topic.assert_called_once_with(['device'], other_topic)

    def test_long_bengali_title_fits_push_payload(self):
        send_notice_notification(12, self.season.id, 'আজকে মিল হয় নাই ' * 100)
        body = self.messaging.Notification.call_args.kwargs['body']
        self.assertLessEqual(len(body.encode('utf-8')), 3003)
        self.messaging.send.assert_called_once()

    def test_permission_failure_returns_safe_503_and_rolls_back_device(self):
        user = self.member('active')
        self.client.force_authenticate(user)
        self.messaging.subscribe_to_topic.return_value.failure_count = 1
        self.messaging.subscribe_to_topic.return_value.errors = [MagicMock(reason='PERMISSION_DENIED')]
        response = self.client.post('/api/v1/auth/push-device', {'token': 'private-device-token'}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertIn('PERMISSION_DENIED', str(response.data))
        self.assertNotIn('private-device-token', str(response.data))
        self.assertFalse(PushDevice.objects.filter(token='private-device-token').exists())

    def test_arbitrary_provider_error_is_not_exposed(self):
        user = self.member('active')
        self.client.force_authenticate(user)
        self.messaging.subscribe_to_topic.return_value.failure_count = 1
        self.messaging.subscribe_to_topic.return_value.errors = [MagicMock(reason='secret-provider-message')]
        response = self.client.post('/api/v1/auth/push-device', {'token': 'device'}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertIn('UNKNOWN_ERROR', str(response.data))
        self.assertNotIn('secret-provider-message', str(response.data))

    def test_v1_unregistered_device_returns_expired_registration(self):
        user = self.member('active')
        self.client.force_authenticate(user)
        self.messaging.subscribe_to_topic.return_value.failure_count = 1
        self.messaging.subscribe_to_topic.return_value.errors = [MagicMock(reason='UNREGISTERED')]
        response = self.client.post('/api/v1/auth/push-device', {'token': 'expired'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushDevice.objects.filter(token='expired').exists())

    def test_registration_keeps_only_current_season_and_mess_after_switch(self):
        user = self.member('active')
        other_mess = Mess.objects.create(name='Other')
        other_season = MessSeason.objects.create(mess=other_mess, name='Other season', start_date=date.today())
        MessMemberShip.objects.create(user=user, mess=other_mess, season=other_season)
        device = PushDevice.objects.create(user=user, token='device', topics=[self.topic, self.mess_topic])
        user.current_season = other_season
        user.save(update_fields=['current_season'])
        self.client.force_authenticate(user)
        response = self.client.post('/api/v1/auth/push-device', {'token': 'device'}, format='json')
        expected = {season_topic(other_season.id), mess_topic(other_mess.id)}
        self.assertEqual(set(response.data['topics']), expected)
        device.refresh_from_db()
        self.assertEqual(set(device.topics), expected)
        self.messaging.unsubscribe_from_topic.assert_any_call(['device'], self.topic)
        self.messaging.unsubscribe_from_topic.assert_any_call(['device'], self.mess_topic)

    def test_notice_does_not_resubscribe_member_to_previous_season(self):
        user = self.member('active')
        other = MessSeason.objects.create(mess=self.mess, name='Selected', start_date=date.today())
        MessMemberShip.objects.create(user=user, mess=self.mess, season=other)
        user.current_season = other
        user.save(update_fields=['current_season'])
        device = PushDevice.objects.create(user=user, token='device', topics=[self.topic, self.mess_topic])
        send_notice_notification(12, self.season.id, 'Notice')
        device.refresh_from_db()
        self.assertEqual(set(device.topics), {season_topic(other.id), self.mess_topic})
        self.messaging.subscribe_to_topic.assert_any_call(['device'], season_topic(other.id))
        for call in self.messaging.subscribe_to_topic.call_args_list:
            self.assertNotEqual(call.args[1], self.topic)
        self.assertEqual(self.messaging.Message.call_args.kwargs['topic'], self.topic)

    def test_no_selected_season_does_not_subscribe_other_memberships(self):
        user = self.member('active')
        user.current_season = None
        user.save(update_fields=['current_season'])
        self.assertEqual(eligible_topics(user.id), set())


class FirebaseCredentialTests(SimpleTestCase):
    def test_inline_json_is_passed_as_certificate_dictionary(self):
        import json
        from django.test import override_settings
        from AuthManagement.push import firebase_messaging
        admin = MagicMock()
        admin.get_app.side_effect = ValueError
        account = {'type': 'service_account', 'private_key': 'key\nline', 'project_id': 'test'}
        with override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=json.dumps(account)):
            with patch.dict('sys.modules', {'firebase_admin': admin}):
                self.assertIs(firebase_messaging(), admin.messaging)
        admin.credentials.Certificate.assert_called_once_with(account)
        admin.initialize_app.assert_called_once_with(admin.credentials.Certificate.return_value)

    def test_empty_json_uses_default_credentials(self):
        from django.test import override_settings
        from AuthManagement.push import firebase_messaging
        admin = MagicMock()
        admin.get_app.side_effect = ValueError
        with override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=''):
            with patch.dict('sys.modules', {'firebase_admin': admin}):
                firebase_messaging()
        admin.initialize_app.assert_called_once_with()

    def test_escaped_single_string_is_decoded_with_private_key_newlines(self):
        import json
        from io import StringIO
        from dotenv import dotenv_values
        from django.test import override_settings
        from AuthManagement.push import firebase_messaging
        admin = MagicMock()
        admin.get_app.side_effect = ValueError
        account = {'type': 'service_account', 'private_key': 'key\nline', 'project_id': 'test'}
        encoded = json.dumps(json.dumps(account, indent=2))
        env = dotenv_values(stream=StringIO("FIREBASE_SERVICE_ACCOUNT_JSON='" + encoded.replace(chr(92), chr(92) * 2) + "'"))
        with override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=env['FIREBASE_SERVICE_ACCOUNT_JSON']):
            with patch.dict('sys.modules', {'firebase_admin': admin}):
                firebase_messaging()
        admin.credentials.Certificate.assert_called_once_with(account)

    def test_malformed_string_does_not_expose_credentials_in_error(self):
        from django.core.exceptions import ImproperlyConfigured
        from django.test import override_settings
        from AuthManagement.push import firebase_messaging
        admin = MagicMock()
        admin.get_app.side_effect = ValueError
        with override_settings(FIREBASE_SERVICE_ACCOUNT_JSON='invalid-secret-value'):
            with patch.dict('sys.modules', {'firebase_admin': admin}):
                with self.assertRaises(ImproperlyConfigured) as error:
                    firebase_messaging()
        self.assertNotIn('invalid-secret-value', str(error.exception))
        admin.initialize_app.assert_not_called()

    def test_base64_value_works_identically_from_dotenv_and_server_environment(self):
        import base64
        import json
        from io import StringIO
        from dotenv import dotenv_values
        from django.test import override_settings
        from AuthManagement.push import firebase_messaging
        account = {'type': 'service_account', 'private_key': 'key\nline', 'project_id': 'test'}
        encoded = base64.b64encode(json.dumps(account, indent=2).encode()).decode()
        local = dotenv_values(stream=StringIO('FIREBASE_SERVICE_ACCOUNT_JSON=' + encoded))
        for value in (encoded, local['FIREBASE_SERVICE_ACCOUNT_JSON']):
            with self.subTest(source=value == encoded):
                admin = MagicMock()
                admin.get_app.side_effect = ValueError
                with override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=value):
                    with patch.dict('sys.modules', {'firebase_admin': admin}):
                        firebase_messaging()
                admin.credentials.Certificate.assert_called_once_with(account)

    def test_base64_invalid_json_is_rejected_without_exposing_value(self):
        import base64
        from django.core.exceptions import ImproperlyConfigured
        from django.test import override_settings
        from AuthManagement.push import firebase_messaging
        for raw in (b'not-json-secret', b'\xff', b'[]'):
            admin = MagicMock()
            admin.get_app.side_effect = ValueError
            value = base64.b64encode(raw).decode()
            with override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=value):
                with patch.dict('sys.modules', {'firebase_admin': admin}):
                    with self.assertRaises(ImproperlyConfigured) as error:
                        firebase_messaging()
            self.assertNotIn(value, str(error.exception))
            admin.initialize_app.assert_not_called()

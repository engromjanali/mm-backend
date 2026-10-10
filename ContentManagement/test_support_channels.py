import io

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from AuthManagement.models import User
from ContentManagement.models import AppSetting, SupportChannel


def logo(name='logo.png'):
    image = io.BytesIO()
    Image.new('RGB', (16, 16), (31, 164, 99)).save(image, 'PNG')
    return SimpleUploadedFile(name, image.getvalue(), content_type='image/png')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SupportChannelTests(APITestCase):
    def tearDown(self):
        cache.clear()

    def test_public_config_returns_only_active_channels_in_order(self):
        SupportChannel.objects.create(name='Hidden', kind='email', destination='hidden@test.com', is_active=False)
        SupportChannel.objects.create(name='Call us', kind='phone', destination='+8801712345678', order=2)
        SupportChannel.objects.create(name='Email us', kind='email', destination='help@test.com', order=1, logo=logo())
        channels = self.client.get('/api/v1/app/config').data['support_channels']
        self.assertEqual([channel['name'] for channel in channels], ['Email us', 'Call us'])
        self.assertEqual(channels[0]['url'], 'mailto:help@test.com')
        self.assertTrue(channels[0]['logo_url'].startswith('http://testserver/media/support_logos/'))
        self.assertEqual(set(channels[0]), {'name', 'kind', 'destination', 'url', 'logo_url'})

    def test_contact_destinations_are_normalized(self):
        for kind, destination, expected in [
            ('email', 'help@test.com', 'mailto:help@test.com'),
            ('telegram', '@mess_support', 'https://t.me/mess_support'),
            ('telegram', 'https://t.me/+inviteToken', 'https://t.me/+inviteToken'),
            ('whatsapp', '+880 (1712) 345-678', 'https://wa.me/8801712345678'),
            ('phone', '01712-345678', 'tel:01712345678'),
            ('website', 'https://example.com/help', 'https://example.com/help'),
        ]:
            with self.subTest(kind=kind, destination=destination):
                channel = SupportChannel(name='Support', kind=kind, destination=destination)
                channel.full_clean()
                self.assertEqual(channel.contact_url, expected)

    def test_invalid_and_unsafe_destinations_are_rejected(self):
        for kind, destination in [('email', 'bad email'), ('phone', '123abc'), ('whatsapp', '01712345678'), ('telegram', 'https://example.com/team'), ('other', 'javascript:alert(1)'), ('website', 'https://user:secret@example.com')]:
            with self.subTest(kind=kind):
                with self.assertRaises(ValidationError):
                    SupportChannel(name='Support', kind=kind, destination=destination).full_clean()

    def test_support_stays_available_during_maintenance_and_keeps_legacy_email(self):
        setting = AppSetting.current()
        setting.support_email = 'legacy@test.com'
        setting.maintenance_mode = True
        setting.save()
        SupportChannel.objects.create(name='Telegram', kind='telegram', destination='mess_support')
        response = self.client.get('/api/v1/app/config')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['support_email'], 'legacy@test.com')
        self.assertEqual(response.data['support_channels'][0]['url'], 'https://t.me/mess_support')
        self.assertEqual(self.client.get('/api/v1/auth/config').data['support_channels'], response.data['support_channels'])

    def test_admin_can_upload_and_remove_a_logo(self):
        admin = User.objects.create_user(email='admin@test.com', phone='01700000001', full_name='Admin', password='pass12345', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        response = self.client.post('/admin/ContentManagement/supportchannel/add/', {'name': 'WhatsApp', 'kind': 'whatsapp', 'destination': '+8801712345678', 'order': 0, 'is_active': 'on', 'logo': logo(), '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        channel = SupportChannel.objects.get()
        self.assertTrue(channel.logo)
        old_name = channel.logo.name
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/admin/ContentManagement/supportchannel/{channel.pk}/change/', {'name': 'WhatsApp', 'kind': 'whatsapp', 'destination': '+8801712345678', 'order': 0, 'is_active': 'on', 'logo-clear': 'on', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        channel.refresh_from_db()
        self.assertFalse(channel.logo)
        self.assertFalse(channel.logo.storage.exists(old_name))

    def test_logo_replacement_and_channel_deletion_remove_old_files(self):
        channel = SupportChannel.objects.create(name='Email', kind='email', destination='help@test.com', logo=logo())
        storage, old_name = channel.logo.storage, channel.logo.name
        with self.captureOnCommitCallbacks(execute=True):
            channel.logo = logo('replacement.png')
            channel.save()
        self.assertFalse(storage.exists(old_name))
        new_name = channel.logo.name
        with self.captureOnCommitCallbacks(execute=True):
            SupportChannel.objects.filter(pk=channel.pk).delete()
        self.assertFalse(storage.exists(new_name))

    def test_large_and_non_image_logos_are_rejected(self):
        image = logo()
        image.size = 2 * 1024 * 1024 + 1
        with self.assertRaises(ValidationError):
            SupportChannel(name='Email', kind='email', destination='help@test.com', logo=image).full_clean()
        with self.assertRaises(ValidationError):
            SupportChannel(name='Email', kind='email', destination='help@test.com', logo=logo('unsafe.svg')).full_clean()

    def test_public_users_cannot_manage_channels(self):
        response = self.client.post('/admin/ContentManagement/supportchannel/add/', {'name': 'Unauthorized'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportChannel.objects.exists())

    def test_disabled_email_does_not_reappear_through_legacy_fallback(self):
        setting = AppSetting.current()
        setting.support_email = 'help@test.com'
        setting.save()
        SupportChannel.objects.create(name='Email', kind='email', destination='help@test.com', is_active=False)
        data = self.client.get('/api/v1/app/config').data
        self.assertEqual(data['support_email'], '')
        self.assertEqual(data['support_channels'], [])

    def test_app_settings_admin_does_not_show_legacy_support_field(self):
        admin = User.objects.create_user(email='admin@test.com', phone='01700000001', full_name='Admin', password='pass12345', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        setting = AppSetting.current()
        response = self.client.get(f'/admin/ContentManagement/appsetting/{setting.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('support_email', response.context['adminform'].form.fields)
        self.assertIn('maintenance_mode', response.context['adminform'].form.fields)

    def test_configured_email_replaces_legacy_email(self):
        setting = AppSetting.current()
        setting.support_email = 'old@test.com'
        setting.save()
        channel = SupportChannel.objects.create(name='Email team', kind='email', destination='new@test.com')
        data = self.client.get('/api/v1/app/config').data
        self.assertEqual(data['support_email'], 'new@test.com')
        self.assertEqual(len(data['support_channels']), 1)
        channel.is_active = False
        channel.save()
        data = self.client.get('/api/v1/app/config').data
        self.assertEqual(data['support_email'], '')
        self.assertEqual(data['support_channels'], [])

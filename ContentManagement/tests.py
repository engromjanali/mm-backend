from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import AppSetting, ContentPage, Faq


class AppContentAPITests(APITestCase):
    """Config, legal pages and FAQs come from Django admin; maintenance mode blocks the API."""

    def tearDown(self):
        AppSetting.objects.all().delete()
        AppSetting.current()  # re-cache defaults so the next test starts clean

    def set(self, **fields):
        setting = AppSetting.current()
        for name, value in fields.items():
            setattr(setting, name, value)
        setting.save()

    # -- config ---------------------------------------------------------------

    def test_config_returns_what_the_admin_set(self):
        self.set(latest_version='1.4.0', minimum_version='1.2.0', update_message='New meal chart!', support_email='help@mess.app')
        data = self.client.get('/api/v1/app/config').data

        self.assertEqual((data['latest_version'], data['minimum_version'], data['version']), ('1.4.0', '1.2.0', '1.4.0'))
        self.assertEqual(data['update_message'], 'New meal chart!')
        self.assertEqual(data['support_email'], 'help@mess.app')
        self.assertFalse(data['maintenance']['enabled'])
        # Older builds still read it here.
        self.assertEqual(self.client.get('/api/v1/auth/config').data['latest_version'], '1.4.0')

    def test_maintenance_mode_blocks_the_api_but_not_config_or_content(self):
        self.set(maintenance_mode=True, maintenance_message='Back at 10 PM.')
        user = User.objects.create_user(email='a@test.com', phone='0171', full_name='A', password='pass12345')
        self.client.force_authenticate(user=user)

        blocked = self.client.get('/api/v1/user/membership/status')
        self.assertEqual(blocked.status_code, 503)
        self.assertEqual(blocked.json(), {'detail': 'Back at 10 PM.', 'maintenance': True})
        self.assertEqual(self.client.get('/api/v1/app/config').data['maintenance'], {'enabled': True, 'message': 'Back at 10 PM.', 'until': None})
        self.assertEqual(self.client.get('/api/v1/app/faqs').status_code, 200)

        self.set(maintenance_mode=False)
        self.assertEqual(self.client.get('/api/v1/user/membership/status').status_code, 200)

    # -- pages and FAQs ---------------------------------------------------------

    def test_page_comes_in_the_app_language_with_english_fallback(self):
        ContentPage.objects.create(kind=ContentPage.TERMS, language='bn', title='শর্তাবলী', body='...')

        self.assertEqual(self.client.get('/api/v1/app/pages/terms-and-conditions', HTTP_X_LOCALIZATION='bn').data['title'], 'শর্তাবলী')
        # No Arabic version yet: English (seeded) is used.
        self.assertEqual(self.client.get('/api/v1/app/pages/terms-and-conditions?lang=ar').data['language'], 'en')
        missing = self.client.get('/api/v1/app/pages/cookie-policy')
        self.assertEqual(missing.status_code, 404)
        self.assertIn("hasn't been published", str(missing.data))

    def test_faqs_are_active_ones_in_order_for_the_language(self):
        Faq.objects.all().delete()
        Faq.objects.create(language='en', question='Second', answer='b', order=2)
        Faq.objects.create(language='en', question='First', answer='a', order=1)
        Faq.objects.create(language='en', question='Hidden', answer='c', order=0, is_active=False)

        self.assertEqual([f['question'] for f in self.client.get('/api/v1/app/faqs', HTTP_X_LOCALIZATION='bn').data], ['First', 'Second'])

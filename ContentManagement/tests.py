from django.core.cache import cache
from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import AppSetting, ContentPage, Faq


class AppContentAPITests(APITestCase):
    """Config, legal pages and FAQs come from Django admin; maintenance mode blocks the API."""

    def tearDown(self):
        cache.clear()
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
        self.assertIn('/privacy-policy/', data['privacy_policy_url'])
        self.assertIn('/terms-and-conditions/', data['terms_and_conditions_url'])
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

    # -- public feature tests ---------------------------------------------------

    def test_direct_public_api_endpoints_work_without_authentication(self):
        # /api/v1/app/privacy-policy and /api/v1/app/terms-and-conditions
        privacy_app = self.client.get('/api/v1/app/privacy-policy')
        self.assertEqual(privacy_app.status_code, 200)
        self.assertEqual(privacy_app.data['kind'], 'privacy-policy')
        self.assertEqual(privacy_app.data['language'], 'en')

        terms_app = self.client.get('/api/v1/app/terms-and-conditions')
        self.assertEqual(terms_app.status_code, 200)
        self.assertEqual(terms_app.data['kind'], 'terms-and-conditions')

        # Root-level /api/v1/privacy-policy and /api/v1/terms-and-conditions
        privacy_api = self.client.get('/api/v1/privacy-policy')
        self.assertEqual(privacy_api.status_code, 200)
        self.assertEqual(privacy_api.data['kind'], 'privacy-policy')

        terms_api = self.client.get('/api/v1/terms-and-conditions')
        self.assertEqual(terms_api.status_code, 200)
        self.assertEqual(terms_api.data['kind'], 'terms-and-conditions')

    def test_public_web_pages_render_html_for_browsers(self):
        # Privacy policy HTML
        for path in ('/privacy-policy/', '/privacy-policy', '/privacy/', '/privacy'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('text/html', response['Content-Type'])
            self.assertContains(response, 'Privacy policy')
            self.assertContains(response, 'Mess Pilot')
            self.assertContains(response, '<h2>Information we collect</h2>')
            self.assertContains(response, 'Account details')

        # Terms and conditions HTML
        for path in ('/terms-and-conditions/', '/terms-and-conditions', '/terms/', '/terms'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('text/html', response['Content-Type'])
            self.assertContains(response, 'Terms and conditions')
            self.assertContains(response, 'Mess Pilot')

    def test_public_web_pages_support_json_accept_header_and_query_param(self):
        # Accept: application/json
        json_resp = self.client.get('/privacy-policy/', HTTP_ACCEPT='application/json')
        self.assertEqual(json_resp.status_code, 200)
        self.assertEqual(json_resp.json()['kind'], 'privacy-policy')

        # ?format=json
        param_resp = self.client.get('/privacy-policy?format=json')
        self.assertEqual(param_resp.status_code, 200)
        self.assertEqual(param_resp.json()['kind'], 'privacy-policy')

    def test_is_public_flag_controls_visibility(self):
        page = ContentPage.objects.get(kind=ContentPage.PRIVACY_POLICY, language='en')
        page.is_public = False
        page.save()

        # API returns 404 when not public
        api_resp = self.client.get('/api/v1/app/privacy-policy')
        self.assertEqual(api_resp.status_code, 404)

        # Web returns 404 when not public
        web_resp = self.client.get('/privacy-policy/')
        self.assertEqual(web_resp.status_code, 404)
        self.assertContains(web_resp, 'Page Not Available', status_code=404)

        # Re-enable
        page.is_public = True
        page.save()
        self.assertEqual(self.client.get('/api/v1/app/privacy-policy').status_code, 200)
        self.assertEqual(self.client.get('/privacy-policy/').status_code, 200)

    def test_public_pages_and_api_accessible_during_maintenance_mode(self):
        self.set(maintenance_mode=True, maintenance_message='Maintenance ongoing')

        # Public web pages should still be 200
        self.assertEqual(self.client.get('/privacy-policy/').status_code, 200)
        self.assertEqual(self.client.get('/terms-and-conditions/').status_code, 200)

        # Public API endpoints should still be 200
        self.assertEqual(self.client.get('/api/v1/app/privacy-policy').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/app/terms-and-conditions').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/privacy-policy').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/terms-and-conditions').status_code, 200)

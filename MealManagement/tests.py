from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from AuthManagement.models import User
from MessManagement.models import Mess, MessMemberShip, MessSeason
from .models import Meals


class MealApiTests(TestCase):
    """End-to-end coverage for the /api/v1/meal/* endpoints."""

    def setUp(self):
        self.client = APIClient()

        self.mess = Mess.objects.create(
            name='Test Mess', email='mess@test.com', phone='0170000000', address='Dhaka',
        )
        self.season = MessSeason.objects.create(
            mess=self.mess, name='Season 1',
            start_date=date(2020, 1, 1), end_date=None, is_active=True,
        )

        self.manager_user = User.objects.create_user(
            email='manager@test.com', phone='0171111111', full_name='Manager Mia', password='pass12345',
        )
        self.member_user = User.objects.create_user(
            email='member@test.com', phone='0172222222', full_name='Member Moe', password='pass12345',
        )

        self.manager = MessMemberShip.objects.create(
            user=self.manager_user, mess=self.mess, season=self.season,
            role='manager', status='active',
        )
        self.member = MessMemberShip.objects.create(
            user=self.member_user, mess=self.mess, season=self.season,
            role='member', status='active',
        )

    def auth(self, membership):
        self.client.force_authenticate(user=membership.user)
        return {'HTTP_MEMBERSHIP_ID': str(membership.id), 'HTTP_SESSION_ID': str(self.season.id)}

    # -- add ---------------------------------------------------------------

    def test_manager_adds_meal_and_total_is_derived(self):
        headers = self.auth(self.manager)
        response = self.client.post(
            '/api/v1/meal/add',
            {'membership_id': self.member.id, 'date': '10-10-2020',
             'breakfast': 1, 'lunch': 2, 'dinner': 1},
            format='json', **headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['data']['total_meals'], 4)
        self.assertEqual(response.data['data']['date'], '10-10-2020')
        self.assertEqual(response.data['data']['member_name'], 'Member Moe')
        self.assertEqual(Meals.objects.get().date, date(2020, 10, 10))

    def test_plain_member_cannot_add(self):
        headers = self.auth(self.member)
        response = self.client.post(
            '/api/v1/meal/add',
            {'membership_id': self.member.id, 'date': '10-10-2020', 'lunch': 1},
            format='json', **headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_duplicate_day_rejected(self):
        headers = self.auth(self.manager)
        payload = {'membership_id': self.member.id, 'date': '10-10-2020', 'lunch': 1}
        self.client.post('/api/v1/meal/add', payload, format='json', **headers)
        response = self.client.post('/api/v1/meal/add', payload, format='json', **headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('date', response.data)

    def test_date_outside_season_rejected(self):
        headers = self.auth(self.manager)
        response = self.client.post(
            '/api/v1/meal/add',
            {'membership_id': self.member.id, 'date': '10-10-2019', 'lunch': 1},
            format='json', **headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_member_from_another_mess_rejected(self):
        other_mess = Mess.objects.create(
            name='Other', email='o@test.com', phone='0179999999', address='CTG',
        )
        other_season = MessSeason.objects.create(
            mess=other_mess, name='S1', start_date=date(2020, 1, 1),
        )
        outsider = MessMemberShip.objects.create(
            user=User.objects.create_user(
                email='out@test.com', phone='0173333333', full_name='Out Olu', password='pass12345',
            ),
            mess=other_mess, season=other_season, role='member', status='active',
        )
        headers = self.auth(self.manager)
        response = self.client.post(
            '/api/v1/meal/add',
            {'membership_id': outsider.id, 'date': '10-10-2020', 'lunch': 1},
            format='json', **headers,
        )
        self.assertEqual(response.status_code, 400)

    # -- update / delete ---------------------------------------------------

    def test_update_by_member_and_date(self):
        headers = self.auth(self.manager)
        self.client.post(
            '/api/v1/meal/add',
            {'membership_id': self.member.id, 'date': '10-10-2020', 'lunch': 1},
            format='json', **headers,
        )
        response = self.client.post(
            '/api/v1/meal/update',
            {'membership_id': self.member.id, 'date': '10-10-2020', 'dinner': 3},
            format='json', **headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data']['dinner'], 3)
        self.assertEqual(response.data['data']['total_meals'], 4)  # lunch 1 preserved

    def test_delete_by_meal_id(self):
        headers = self.auth(self.manager)
        created = self.client.post(
            '/api/v1/meal/add',
            {'membership_id': self.member.id, 'date': '10-10-2020', 'lunch': 1},
            format='json', **headers,
        )
        meal_id = created.data['data']['id']
        response = self.client.delete(
            '/api/v1/meal/delete', {'meal_id': meal_id}, format='json', **headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Meals.objects.count(), 0)

    # -- list --------------------------------------------------------------

    def _seed(self):
        headers = self.auth(self.manager)
        for day, member in [('10-10-2020', self.member), ('15-10-2020', self.member),
                            ('20-10-2023', self.member), ('10-10-2020', self.manager)]:
            self.client.post(
                '/api/v1/meal/add',
                {'membership_id': member.id, 'date': day,
                 'breakfast': 1, 'lunch': 1, 'dinner': 1},
                format='json', **headers,
            )
        return headers

    def test_list_returns_only_callers_meals(self):
        self._seed()
        headers = self.auth(self.member)
        response = self.client.get('/api/v1/meal/list', **headers)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_size'], 3)
        self.assertTrue(all(r['membership_id'] == self.member.id for r in response.data['data']))
        self.assertEqual(response.data['summary']['total_meals'], 9)

    def test_list_exact_date_filter(self):
        self._seed()
        headers = self.auth(self.member)
        response = self.client.get('/api/v1/meal/list?date=10-10-2020', **headers)
        self.assertEqual(response.data['total_size'], 1)
        self.assertEqual(response.data['filters']['date'], '10-10-2020')

    def test_list_date_range_filter_is_chronological(self):
        self._seed()
        headers = self.auth(self.member)
        response = self.client.get(
            '/api/v1/meal/list?start_date=10-10-2020&end_date=20-10-2023', **headers,
        )
        self.assertEqual(response.data['total_size'], 3)

        narrow = self.client.get(
            '/api/v1/meal/list?start_date=11-10-2020&end_date=31-12-2020', **headers,
        )
        self.assertEqual(narrow.data['total_size'], 1)
        self.assertEqual(narrow.data['data'][0]['date'], '15-10-2020')

    def test_list_all_covers_every_member(self):
        headers = self._seed()
        response = self.client.get('/api/v1/meal/list-all', **headers)
        self.assertEqual(response.data['total_size'], 4)
        self.assertEqual(response.data['summary']['total_meals'], 12)
        self.assertEqual(len(response.data['member_summary']), 2)

    def test_list_all_filtered_by_membership(self):
        headers = self._seed()
        response = self.client.get(
            f'/api/v1/meal/list-all?membership_id={self.manager.id}', **headers,
        )
        self.assertEqual(response.data['total_size'], 1)

    def test_bad_date_param_returns_400(self):
        headers = self.auth(self.member)
        response = self.client.get('/api/v1/meal/list?date=notadate', **headers)
        self.assertEqual(response.status_code, 400)

    def test_missing_headers_rejected(self):
        self.client.force_authenticate(user=self.member_user)
        response = self.client.get('/api/v1/meal/list')
        self.assertEqual(response.status_code, 403)

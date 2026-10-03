from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from AuthManagement.models import User
from CostManagement.models import Cost
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

        self.mess.manager = self.manager_user
        self.mess.save()
        self.manager = MessMemberShip.objects.create(
            user=self.manager_user, mess=self.mess, season=self.season,
            status='active',
        )
        self.member = MessMemberShip.objects.create(
            user=self.member_user, mess=self.mess, season=self.season,
            status='active',
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
            mess=other_mess, season=other_season, status='active',
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


class MealTestBase(TestCase):
    """A mess with a manager (Manager Mia) and a member (Alice), signed in as the manager."""

    DAY = '2026-01-10'

    def setUp(self):
        self.client = APIClient()
        self.mess = Mess.objects.create(name='Test Mess')
        self.season = MessSeason.objects.create(mess=self.mess, name='Season 1', start_date=date(2020, 1, 1), is_active=True)
        self.manager_user = User.objects.create_user(email='manager@test.com', phone='0171111111', full_name='Manager Mia', password='pass12345')
        self.alice_user = User.objects.create_user(email='alice@test.com', phone='0172222222', full_name='Alice', password='pass12345')
        self.mess.manager = self.manager_user
        self.mess.save()
        self.manager = MessMemberShip.objects.create(user=self.manager_user, mess=self.mess, season=self.season)
        self.alice = MessMemberShip.objects.create(user=self.alice_user, mess=self.mess, season=self.season)
        self.client.force_authenticate(user=self.manager_user)

    def bulk(self, meals, day=DAY):
        return self.client.post('/api/v1/admin/meals/bulk', {'date': day, 'meals': meals}, format='json')

    def row(self, member, breakfast=1, lunch=1, dinner=1):
        return {'member_id': member.id, 'breakfast': breakfast, 'lunch': lunch, 'dinner': dinner}

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))


class AdminMealApiTests(MealTestBase):
    """Coverage for the manager's /api/v1/admin/meals endpoints."""

    # -- access --------------------------------------------------------------

    def test_plain_member_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(user=self.alice_user)
        self.assertEqual(self.client.get('/api/v1/admin/meals').status_code, 403)
        self.assertEqual(self.bulk([self.row(self.alice)]).status_code, 403)
        self.assertEqual(self.client.patch('/api/v1/admin/meals', {'member_id': self.alice.id, 'date': self.DAY, 'lunch': 1}, format='json').status_code, 403)
        self.assertEqual(self.client.delete('/api/v1/admin/meals', {'member_id': self.alice.id, 'date': self.DAY}, format='json').status_code, 403)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/v1/admin/meals').status_code, (401, 403))

    # -- read ----------------------------------------------------------------

    def test_payload_lists_manager_as_member_with_zero_rate(self):
        data = self.client.get('/api/v1/admin/meals').data
        self.assertEqual([m['name'] for m in data['members']], ['Alice', 'Manager Mia'])
        self.assertEqual(data['meal_rate'], 0.0)
        self.assertEqual(data['entries'], [])

    # -- bulk add ------------------------------------------------------------

    def test_bulk_adds_half_meals_and_derives_rate(self):
        Cost.objects.create(season=self.season, performed_by=self.manager, amount=Decimal('500'))
        response = self.bulk([self.row(self.manager, 1, 1.5, 1), self.row(self.alice, 0, 1, 0.5)])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['mutation'], {'action': 'add', 'created_count': 2, 'updated_count': 0})
        self.assertEqual(response.data['summary']['total_meals'], 5.0)
        self.assertEqual(response.data['meal_rate'], 100.0)
        mine = next(e for e in response.data['entries'] if e['member_id'] == self.manager.id)
        self.assertEqual((mine['lunch'], mine['total'], mine['date']), (1.5, 3.5, self.DAY))

    def test_bulk_rejects_a_day_that_already_has_meals(self):
        self.assertEqual(self.bulk([self.row(self.manager)]).status_code, 201)
        # Even for a member who has no meal yet that day.
        response = self.bulk([self.row(self.alice)])
        self.assertRejected(response, 'Meals for 10-01-2026 are already added. Edit them from Manage meals.', 409)
        self.assertFalse(Meals.objects.filter(mess_member=self.alice).exists())

    def test_bulk_is_all_or_nothing(self):
        response = self.bulk([self.row(self.manager), self.row(self.alice, 5, 0, 0)])
        self.assertRejected(response, 'Row 2: Breakfast must be between 0 and 3 meals.')
        self.assertEqual(Meals.objects.count(), 0)

    def test_bulk_validates_meal_counts(self):
        self.assertRejected(self.bulk([self.row(self.alice, 1.25)]), 'Breakfast must be a whole or half meal')
        self.assertRejected(self.bulk([self.row(self.alice, -1)]), 'Breakfast must be between 0 and 3 meals.')
        self.assertRejected(self.bulk([self.row(self.alice, 1, 'lots')]), 'Row 1: A valid number is required.')
        self.assertRejected(self.bulk([self.row(self.alice, 0, 0, 0)]), 'Add at least one meal for Alice.')
        self.assertRejected(self.bulk([{'breakfast': 1}]), 'Row 1: member_id is required.')
        self.assertRejected(self.bulk(['oops']), 'Row 1 must be an object')

    def test_bulk_validates_members(self):
        self.assertRejected(self.bulk([self.row(self.alice), self.row(self.alice)]), 'Alice is listed more than once.')
        self.assertRejected(self.bulk([{'member_id': 9999, 'lunch': 1}]), 'no member with ID 9999 in the current season')

        other_mess = Mess.objects.create(name='Other')
        other_season = MessSeason.objects.create(mess=other_mess, name='S', start_date=date(2020, 1, 1))
        bob = User.objects.create_user(email='bob@test.com', phone='0173333333', full_name='Bob', password='pass12345')
        outsider = MessMemberShip.objects.create(user=bob, mess=other_mess, season=other_season)
        self.assertRejected(self.bulk([self.row(outsider)]), f'no member with ID {outsider.id} in the current season')

        self.alice.left_at = timezone.now()
        self.alice.save()
        self.assertRejected(self.bulk([self.row(self.alice)]), 'Alice is no longer an active member of this season.')

    def test_bulk_validates_date_and_list(self):
        self.assertRejected(self.client.post('/api/v1/admin/meals/bulk', {'meals': [self.row(self.alice)]}, format='json'), 'date')
        self.assertRejected(self.bulk([self.row(self.alice)], day='31-02-2026'), 'Date has wrong format')
        self.assertRejected(self.bulk([self.row(self.alice)], day='2019-12-31'), 'Date is before the season started (01-01-2020).')
        future = (timezone.localdate() + timedelta(days=2)).isoformat()
        self.assertRejected(self.bulk([self.row(self.alice)], day=future), "Meals can't be added for a future date.")
        self.assertRejected(self.bulk([]), 'This list may not be empty.')
        self.assertRejected(self.client.post('/api/v1/admin/meals/bulk', {'date': self.DAY, 'meals': 'x'}, format='json'), 'Expected a list')

        self.season.end_date = date(2025, 12, 31)
        self.season.save()
        self.assertRejected(self.bulk([self.row(self.alice)]), 'Date is after the season ended (31-12-2025).')

    # -- update --------------------------------------------------------------

    def test_update_changes_only_sent_counts(self):
        self.bulk([self.row(self.alice, 1, 1, 1)])
        response = self.client.patch('/api/v1/admin/meals', {'member_id': self.alice.id, 'date': self.DAY, 'dinner': 2.5}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['mutation']['updated_count'], 1)
        meal = Meals.objects.get(mess_member=self.alice)
        self.assertEqual((meal.breakfast, meal.dinner, meal.total_meals), (Decimal('1'), Decimal('2.5'), Decimal('4.5')))

    def test_update_validation(self):
        self.bulk([self.row(self.alice, 1, 0, 0)])
        patch = lambda body: self.client.patch('/api/v1/admin/meals', {'member_id': self.alice.id, 'date': self.DAY, **body}, format='json')
        self.assertRejected(patch({}), 'Send breakfast, lunch or dinner to update.')
        self.assertRejected(patch({'breakfast': 0}), "A meal can't be all zero. Delete it instead.")
        self.assertRejected(patch({'lunch': 4}), 'Lunch must be between 0 and 3 meals.')
        missing = self.client.patch('/api/v1/admin/meals', {'member_id': self.manager.id, 'date': self.DAY, 'lunch': 1}, format='json')
        self.assertRejected(missing, 'Manager Mia has no meal on 10-01-2026.', 404)
        self.assertRejected(self.client.patch('/api/v1/admin/meals', {'date': self.DAY, 'lunch': 1}, format='json'), 'member_id')

    # -- delete --------------------------------------------------------------

    def test_delete_by_body_or_query_params(self):
        self.bulk([self.row(self.alice), self.row(self.manager)])
        by_body = self.client.delete('/api/v1/admin/meals', {'member_id': self.alice.id, 'date': self.DAY}, format='json')
        self.assertEqual(by_body.status_code, 200, by_body.data)
        self.assertEqual(by_body.data['mutation']['action'], 'delete')
        by_query = self.client.delete(f'/api/v1/admin/meals?member_id={self.manager.id}&date={self.DAY}')
        self.assertEqual(by_query.status_code, 200, by_query.data)
        self.assertEqual(Meals.objects.count(), 0)
        again = self.client.delete('/api/v1/admin/meals', {'member_id': self.alice.id, 'date': self.DAY}, format='json')
        self.assertRejected(again, 'Alice has no meal on 10-01-2026.', 404)



class MyMealApiTests(MealTestBase):
    """Coverage for the member's own GET /api/v1/user/meals."""

    def test_each_member_sees_only_own_meals_with_season_rate(self):
        Cost.objects.create(season=self.season, performed_by=self.manager, amount=Decimal('500'))
        self.bulk([self.row(self.manager, 1, 1.5, 1), self.row(self.alice, 0, 1, 0.5)])

        mine = self.client.get('/api/v1/user/meals')
        self.assertEqual(mine.status_code, 200, mine.data)
        self.assertEqual(mine.data['user_name'], 'Manager Mia')
        self.assertEqual(mine.data['meal_rate'], 100.0)
        self.assertEqual(mine.data['summary'], {'total_meals': 3.5, 'meal_cost': 350.0, 'days': 1})
        self.assertEqual(mine.data['days'], [{'date': self.DAY, 'breakfast': 1.0, 'lunch': 1.5, 'dinner': 1.0, 'total': 3.5}])

        self.client.force_authenticate(user=self.alice_user)
        alice = self.client.get('/api/v1/user/meals').data
        self.assertEqual(alice['summary']['total_meals'], 1.5)
        self.assertEqual(alice['meal_rate'], 100.0)

    def test_empty_season_has_zero_rate(self):
        data = self.client.get('/api/v1/user/meals').data
        self.assertEqual((data['meal_rate'], data['days'], data['summary']['total_meals']), (0.0, [], 0.0))

    def test_user_without_active_mess_is_told_why(self):
        loner = User.objects.create_user(email='loner@test.com', phone='0174444444', full_name='Loner', password='pass12345')
        self.client.force_authenticate(user=loner)
        self.assertRejected(self.client.get('/api/v1/user/meals'), 'You are not connected to an active mess.')

        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/v1/user/meals').status_code, (401, 403))

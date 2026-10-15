from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from AuthManagement.models import User
from CostManagement.models import Cost
from DepositManagement.models import Deposit
from FundManagement.models import Fund
from MealManagement.models import Meals
from MessManagement.models import Mess
from .models import MessMemberShip, MessSeason


class MyMessAPITests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='alice', password='pass12345')
        self.bob = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.client.force_authenticate(user=self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July 2026', 'address': 'Mirpur 10'}, format='json')
        for user in (self.alice, self.bob):
            self.client.force_authenticate(user=self.manager)
            invite = self.client.post('/api/v1/admin/invites', {'user_id': user.id}, format='json').data
            self.client.force_authenticate(user=user)
            self.client.post('/api/v1/user/invites/accept', {'invite_code': invite['invite_code']}, format='json')
        self.manager_m = MessMemberShip.objects.get(user=self.manager)
        self.mess = self.manager_m.mess
        self.mess.acting_manager = self.bob
        self.mess.save()

    def get_mess(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get('/api/v1/user/mess')

    def test_member_sees_mess_season_leadership_and_members(self):
        response = self.get_mess(self.alice)
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        self.assertEqual((data['name'], data['address'], data['map_url'], data['season']['name'], data['my_role']), ('Green House', 'Mirpur 10', '', 'July 2026', 'member'))
        self.assertEqual(data['manager']['name'], 'Manager Mia')
        self.assertEqual(data['acting_manager']['phone'], '01733333333')
        # Manager first, then acting manager, then the rest by name.
        self.assertEqual([(m['name'], m['role']) for m in data['members']], [('Manager Mia', 'manager'), ('Bob', 'acting_manager'), ('alice', 'member')])
        self.assertEqual(data['permissions'], {'can_edit': False, 'can_transfer': False, 'can_leave': True})

    def test_permissions_follow_role(self):
        self.assertEqual(self.get_mess(self.manager).data['permissions'], {'can_edit': True, 'can_transfer': True, 'can_leave': False})
        self.assertEqual(self.get_mess(self.bob).data['permissions'], {'can_edit': True, 'can_transfer': False, 'can_leave': True})

    def test_season_stats(self):
        season = self.manager_m.season
        alice_m = MessMemberShip.objects.get(user=self.alice)
        Meals(mess_season=season, mess_member=self.manager_m, date=season.start_date, breakfast=1, lunch=1.5, dinner=1).save()
        Meals(mess_season=season, mess_member=alice_m, date=season.start_date, lunch=1, dinner=0.5).save()
        Cost.objects.create(season=season, performed_by=self.manager_m, amount=Decimal('500'))
        Deposit.objects.create(season=season, performed_by=alice_m, amount=Decimal('2000'))
        Deposit.objects.create(season=season, performed_by=alice_m, amount=Decimal('-300'))
        Fund.objects.create(mess=self.mess, amount=Decimal('800'), date=date(2026, 7, 1))

        stats = self.get_mess(self.alice).data['stats']
        self.assertEqual(stats, {'members': 3, 'total_meals': 5.0, 'meal_rate': 100.0, 'total_cost': 500.0, 'total_deposit': 1700.0, 'fund_balance': 800.0})

    def test_members_who_left_are_not_listed(self):
        self.client.force_authenticate(user=self.alice)
        self.client.post('/api/v1/user/membership/leave')
        data = self.get_mess(self.manager).data
        self.assertEqual([m['name'] for m in data['members']], ['Manager Mia', 'Bob'])
        self.assertEqual(data['stats']['members'], 2)
        # Alice can still open the season and see its previous data.
        self.assertEqual(self.get_mess(self.alice).data['name'], self.mess.name)

    def test_requires_an_active_mess_and_login(self):
        loner = User.objects.create_user(email='loner@test.com', phone='01744444444', full_name='Loner', password='pass12345')
        response = self.get_mess(loner)
        self.assertEqual((response.status_code, str(response.data['detail'])), (400, 'You are not connected to an active mess.'))
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/v1/user/mess').status_code, (401, 403))

    def test_manager_and_acting_manager_can_update_mess_details(self):
        for user in (self.manager, self.bob):
            self.client.force_authenticate(user=user)
            response = self.client.patch('/api/v1/user/mess', {'name': 'Updated House', 'address': 'New address', 'email': 'house@test.com', 'phone': '01755555555'}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.mess.refresh_from_db()
            self.assertEqual((self.mess.name, self.mess.address, self.mess.email, self.mess.phone), ('Updated House', 'New address', 'house@test.com', '01755555555'))

    def test_member_and_anonymous_users_cannot_update_mess(self):
        self.client.force_authenticate(user=self.alice)
        self.assertEqual(self.client.patch('/api/v1/user/mess', {'name': 'Unauthorized'}, format='json').status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.patch('/api/v1/user/mess', {'name': 'Unauthorized'}, format='json').status_code, (401, 403))
        self.mess.refresh_from_db()
        self.assertEqual(self.mess.name, 'Green House')

    def test_update_validates_details_and_cannot_change_leadership(self):
        self.client.force_authenticate(user=self.manager)
        for data in ({'name': ' '}, {'name': 'x' * 101}, {'email': 'invalid'}, {'phone': '1' * 21}, {'address': 'x' * 256}):
            self.assertEqual(self.client.patch('/api/v1/user/mess', data, format='json').status_code, 400)
        response = self.client.patch('/api/v1/user/mess', {'address': '', 'email': '', 'phone': '', 'manager': self.alice.id, 'acting_manager': self.alice.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.mess.refresh_from_db()
        self.assertEqual((self.mess.manager_id, self.mess.acting_manager_id), (self.manager.id, self.bob.id))
        self.assertEqual(self.mess.name, 'Green House')

    def test_update_cannot_target_another_mess(self):
        other = Mess.objects.create(name='Other House', manager=self.alice)
        self.client.force_authenticate(user=self.manager)
        response = self.client.patch('/api/v1/user/mess', {'id': other.id, 'mess_id': other.id, 'name': 'My updated mess'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        other.refresh_from_db()
        self.mess.refresh_from_db()
        self.assertEqual(other.name, 'Other House')
        self.assertEqual(self.mess.name, 'My updated mess')

    def test_disabled_manager_cannot_update_mess(self):
        self.manager_m.status = 'disabled'
        self.manager_m.save()
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(self.client.patch('/api/v1/user/mess', {'name': 'Unauthorized'}, format='json').status_code, 403)
        self.mess.refresh_from_db()
        self.assertEqual(self.mess.name, 'Green House')

    def test_manager_can_set_google_maps_location(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.patch('/api/v1/user/mess', {'latitude': 23.8103, 'longitude': 90.4125}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.mess.refresh_from_db()
        self.assertEqual((self.mess.latitude, self.mess.longitude), (Decimal('23.8103000'), Decimal('90.4125000')))
        self.assertEqual(self.mess.map_url, 'https://www.google.com/maps/search/?api=1&query=23.8103,90.4125')

    def test_mess_location_requires_valid_coordinate_pair(self):
        self.client.force_authenticate(user=self.manager)
        for data in ({'latitude': 23.8}, {'longitude': 90.4}, {'latitude': 91, 'longitude': 90}, {'latitude': 23, 'longitude': 181}):
            response = self.client.patch('/api/v1/user/mess', data, format='json')
            self.assertEqual(response.status_code, 400, response.data)

    @override_settings(GOOGLE_MAPS_API_KEY='server-secret')
    @patch('MessManagement.mess_views.urlopen')
    def test_manager_can_search_locations_without_exposing_key(self, mocked_urlopen):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({'places': [{'displayName': {'text': 'Dhaka'}, 'formattedAddress': 'Dhaka, Bangladesh', 'location': {'latitude': 23.81, 'longitude': 90.41}}]}).encode()
        mocked_urlopen.return_value = FakeResponse()
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/v1/user/mess/location-search?q=Dhaka')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, [{'name': 'Dhaka', 'address': 'Dhaka, Bangladesh', 'latitude': 23.81, 'longitude': 90.41}])
        self.assertNotIn('server-secret', str(response.data))

    def test_member_cannot_search_locations(self):
        self.client.force_authenticate(user=self.alice)
        self.assertEqual(self.client.get('/api/v1/user/mess/location-search?q=Dhaka').status_code, 403)

    def test_member_financial_totals_are_only_visible_to_managers(self):
        season = self.manager_m.season
        alice_m = MessMemberShip.objects.get(user=self.alice)
        for amount in ('2000', '500', '-300'):
            Deposit.objects.create(season=season, performed_by=alice_m, amount=Decimal(amount))
        Meals.objects.create(mess_season=season, mess_member=alice_m, date=season.start_date, lunch=Decimal('1.5'), dinner=1)
        Cost.objects.create(season=season, performed_by=self.manager_m, amount=Decimal('250'))
        for user in (self.manager, self.bob):
            data = self.get_mess(user).data
            rows = {row['id']: row for row in data['member_stats']}
            self.assertEqual(rows[alice_m.id], {'id': alice_m.id, 'name': 'alice', 'deposit': 2200.0, 'meal': 2.5})
            self.assertEqual((rows[self.manager_m.id]['deposit'], rows[self.manager_m.id]['meal']), (0, 0))
            self.assertEqual(data['stats']['meal_rate'], 100)
        self.assertNotIn('member_stats', self.get_mess(self.alice).data)

    def test_member_totals_follow_selected_season_and_keep_departed_members(self):
        alice_m = MessMemberShip.objects.get(user=self.alice)
        Deposit.objects.create(season=self.manager_m.season, performed_by=alice_m, amount=Decimal('500'))
        alice_m.left_at = self.manager_m.joined_at
        alice_m.status = 'inactive'
        alice_m.save()
        rows = {row['id']: row for row in self.get_mess(self.manager).data['member_stats']}
        self.assertEqual(rows[alice_m.id]['deposit'], 500)
        other_season = MessSeason.objects.create(mess=self.mess, name='Other season', start_date=self.manager_m.season.start_date)
        selected = MessMemberShip.objects.create(user=self.manager, mess=self.mess, season=other_season)
        Deposit.objects.create(season=other_season, performed_by=selected, amount=Decimal('900'))
        self.manager.current_membership = selected
        self.manager.save(update_fields=['current_membership'])
        data = self.get_mess(self.manager).data
        self.assertEqual(data['season']['id'], other_season.id)
        self.assertEqual(data['member_stats'], [{'id': selected.id, 'name': 'Manager Mia', 'deposit': 900.0, 'meal': 0.0}])

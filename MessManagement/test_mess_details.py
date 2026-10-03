from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from AuthManagement.models import User
from CostManagement.models import Cost
from DepositManagement.models import Deposit
from FundManagement.models import Fund
from MealManagement.models import Meals
from .models import MessMemberShip


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
        self.assertEqual((data['name'], data['address'], data['season']['name'], data['my_role']), ('Green House', 'Mirpur 10', 'July 2026', 'member'))
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
        # Alice has no active mess any more.
        self.assertEqual(self.get_mess(self.alice).data, {'detail': 'You are not connected to an active mess.'})

    def test_requires_an_active_mess_and_login(self):
        loner = User.objects.create_user(email='loner@test.com', phone='01744444444', full_name='Loner', password='pass12345')
        response = self.get_mess(loner)
        self.assertEqual((response.status_code, str(response.data['detail'])), (400, 'You are not connected to an active mess.'))
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/v1/user/mess').status_code, (401, 403))

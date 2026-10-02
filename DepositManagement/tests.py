from rest_framework.test import APITestCase

from AuthManagement.models import User
from MessManagement.models import MessMemberShip
from .models import Deposit


class DepositAPITests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.client.force_authenticate(user=self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July 2026'}, format='json')
        invite = self.client.post('/api/v1/admin/invites', {'user_id': self.alice.id}, format='json').data
        self.client.force_authenticate(user=self.alice)
        self.client.post('/api/v1/user/invites/accept', {'invite_code': invite['invite_code']}, format='json')
        self.manager_m = MessMemberShip.objects.get(user=self.manager)
        self.alice_m = MessMemberShip.objects.get(user=self.alice)
        self.today = self.manager_m.season.start_date.isoformat()

    def add(self, member, amount, **extra):
        self.client.force_authenticate(user=self.manager)
        return self.client.post('/api/v1/admin/deposits', {'member_id': member.id, 'amount': amount, 'date': self.today, **extra}, format='json')

    def test_manager_adds_credit_and_debit_with_signed_amounts(self):
        credit = self.add(self.alice_m, '1500', note='Monthly')
        self.assertEqual(credit.status_code, 201, credit.data)
        self.assertEqual(credit.data['type'], 'credit')
        self.assertEqual(credit.data['member_name'], 'Alice')
        self.assertEqual(credit.data['recorded_by'], 'Manager Mia')
        debit = self.add(self.alice_m, '-200')
        self.assertEqual(debit.data['type'], 'debit')
        self.assertEqual(self.add(self.alice_m, '0').status_code, 400)

    def test_members_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(user=self.alice)
        self.assertEqual(self.client.get('/api/v1/admin/deposits').status_code, 403)
        self.assertEqual(self.client.post('/api/v1/admin/deposits', {'member_id': self.alice_m.id, 'amount': 10}, format='json').status_code, 403)

    def test_list_filters_and_totals(self):
        self.add(self.alice_m, '1000')
        self.add(self.alice_m, '-300')
        self.add(self.manager_m, '2000')

        everything = self.client.get('/api/v1/admin/deposits').data
        self.assertEqual(everything['summary'], {'credit': 3000.0, 'debit': 300.0, 'net': 2700.0, 'entries': 3})

        alice_only = self.client.get('/api/v1/admin/deposits', {'member_id': self.alice_m.id}).data
        self.assertEqual(alice_only['summary']['net'], 700.0)
        self.assertEqual({d['member_name'] for d in alice_only['data']}, {'Alice'})

        same_day = self.client.get('/api/v1/admin/deposits', {'date': self.today}).data
        self.assertEqual(same_day['summary']['entries'], 3)
        in_range = self.client.get('/api/v1/admin/deposits', {'start': '01-01-2000', 'end': '02-01-2000'}).data
        self.assertEqual(in_range['data'], [])

    def test_manager_is_a_member_and_sees_own_deposits(self):
        self.add(self.manager_m, '500')
        self.add(self.alice_m, '900')

        mine = self.client.get('/api/v1/user/deposits').data
        self.assertEqual(mine['summary']['net'], 500.0)
        self.assertEqual(len(mine['data']), 1)

        summary = self.client.get('/api/v1/admin/deposits/summary').data
        self.assertEqual(summary['mine']['net'], 500.0)
        self.assertEqual(summary['summary']['members'], 2)
        self.assertEqual([b['member_name'] for b in summary['member_balances']], ['Alice', 'Manager Mia'])

    def test_summary_includes_members_without_deposits(self):
        self.add(self.manager_m, '500')
        summary = self.client.get('/api/v1/admin/deposits/summary').data
        self.assertEqual(summary['summary']['active_members'], 1)
        alice = next(b for b in summary['member_balances'] if b['member_name'] == 'Alice')
        self.assertEqual(alice['entries'], 0)

    def test_update_and_delete(self):
        deposit_id = self.add(self.alice_m, '1000').data['id']
        updated = self.client.patch(f'/api/v1/admin/deposits/{deposit_id}', {'amount': '-50', 'note': 'Refund'}, format='json')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['type'], 'debit')
        self.assertEqual(updated.data['note'], 'Refund')
        self.assertEqual(self.client.delete(f'/api/v1/admin/deposits/{deposit_id}').status_code, 200)
        self.assertFalse(Deposit.objects.exists())

    def test_cannot_record_for_member_of_another_mess_or_outside_season(self):
        outsider = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.client.force_authenticate(user=outsider)
        self.client.post('/api/v1/user/messes/create', {'name': 'Other', 'season_name': 'S1'}, format='json')
        outsider_m = MessMemberShip.objects.get(user=outsider)

        self.assertEqual(self.add(outsider_m, '100').status_code, 400)
        self.client.force_authenticate(user=self.manager)
        before_season = self.client.post('/api/v1/admin/deposits', {'member_id': self.alice_m.id, 'amount': '100', 'date': '01-01-2000'}, format='json')
        self.assertEqual(before_season.status_code, 400)

from rest_framework.test import APITestCase

from AuthManagement.models import User
from MessManagement.models import MessMemberShip
from .models import Fund


class FundAPITests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.client.force_authenticate(user=self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July 2026'}, format='json')
        invite = self.client.post('/api/v1/admin/invites', {'user_id': self.alice.id}, format='json').data
        self.client.force_authenticate(user=self.alice)
        self.client.post('/api/v1/user/invites/accept', {'invite_code': invite['invite_code']}, format='json')
        self.season = MessMemberShip.objects.get(user=self.manager).season
        self.today = self.season.start_date.isoformat()

    def add(self, amount, **extra):
        self.client.force_authenticate(user=self.manager)
        return self.client.post('/api/v1/admin/funds', {'amount': amount, 'date': self.today, **extra}, format='json')

    def test_manager_adds_credit_and_debit_with_signed_amounts(self):
        credit = self.add('2000', note='Gas bill reserve')
        self.assertEqual(credit.status_code, 201, credit.data)
        self.assertEqual(credit.data['type'], 'credit')
        self.assertEqual(credit.data['note'], 'Gas bill reserve')
        self.assertEqual(credit.data['recorded_by'], 'Manager Mia')
        self.assertEqual(self.add('-500').data['type'], 'debit')
        self.assertEqual(self.add('0').status_code, 400)

    def test_members_can_read_but_not_change_funds(self):
        fund_id = self.add('1000').data['id']
        self.client.force_authenticate(user=self.alice)

        listing = self.client.get('/api/v1/user/funds')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['summary']['net'], 1000.0)

        self.assertEqual(self.client.post('/api/v1/admin/funds', {'amount': 10}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/admin/funds/{fund_id}', {'amount': 10}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/v1/admin/funds/{fund_id}').status_code, 403)

    def test_manager_reads_through_the_user_endpoint_too(self):
        self.add('300')
        self.assertEqual(self.client.get('/api/v1/user/funds').data['summary']['entries'], 1)

    def test_list_filters_totals_and_season_balance(self):
        self.add('1000')
        self.add('-300')

        everything = self.client.get('/api/v1/user/funds').data
        self.assertEqual(everything['summary'], {'credit': 1000.0, 'debit': 300.0, 'net': 700.0, 'entries': 2})
        self.assertEqual(everything['season_balance'], 700.0)

        same_day = self.client.get('/api/v1/user/funds', {'date': self.today}).data
        self.assertEqual(same_day['summary']['entries'], 2)

        old_range = self.client.get('/api/v1/user/funds', {'start_date': '01-01-2000', 'end_date': '02-01-2000'}).data
        self.assertEqual(old_range['data'], [])
        self.assertEqual(old_range['season_balance'], 700.0)

        bad_range = self.client.get('/api/v1/user/funds', {'start_date': '02-01-2000', 'end_date': '01-01-2000'})
        self.assertEqual(bad_range.status_code, 400)

    def test_update_and_delete(self):
        fund_id = self.add('1000').data['id']
        updated = self.client.patch(f'/api/v1/admin/funds/{fund_id}', {'amount': '-50', 'note': 'Refund'}, format='json')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['type'], 'debit')
        self.assertEqual(updated.data['note'], 'Refund')
        self.assertEqual(self.client.delete(f'/api/v1/admin/funds/{fund_id}').status_code, 200)
        self.assertFalse(Fund.objects.exists())
        self.assertEqual(self.client.delete(f'/api/v1/admin/funds/{fund_id}').status_code, 404)

    def test_date_outside_season_gives_a_specific_error(self):
        response = self.add('100', date='01-01-2000')
        self.assertEqual(response.status_code, 400)
        self.assertIn('before the season started', str(response.data['date']))

    def test_funds_are_isolated_per_mess(self):
        fund_id = self.add('100').data['id']
        outsider = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.client.force_authenticate(user=outsider)
        self.client.post('/api/v1/user/messes/create', {'name': 'Other', 'season_name': 'S1'}, format='json')

        self.assertEqual(self.client.get('/api/v1/user/funds').data['data'], [])
        self.assertEqual(self.client.patch(f'/api/v1/admin/funds/{fund_id}', {'amount': 1}, format='json').status_code, 404)

    def test_user_without_a_mess_gets_a_specific_error(self):
        loner = User.objects.create_user(email='lone@test.com', phone='01744444444', full_name='Lone', password='pass12345')
        self.client.force_authenticate(user=loner)
        response = self.client.get('/api/v1/user/funds')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(str(response.data['detail']), 'You are not connected to an active mess.')

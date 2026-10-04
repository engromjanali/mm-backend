from rest_framework.test import APITestCase

from AuthManagement.models import User
from MessManagement.models import MessMemberShip
from .models import Cost, CostBreakdown


class CostAPITests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.client.force_authenticate(user=self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July 2026'}, format='json')
        invite = self.client.post('/api/v1/admin/invites', {'user_id': self.alice.id}, format='json').data
        self.client.force_authenticate(user=self.alice)
        self.client.post('/api/v1/user/invites/accept', {'invite_code': invite['invite_code']}, format='json')
        self.manager_member = MessMemberShip.objects.get(user=self.manager)
        self.alice_member = MessMemberShip.objects.get(user=self.alice)
        self.today = self.manager_member.season.start_date.isoformat()

    def add(self, items=None, member=None, **extra):
        self.client.force_authenticate(user=self.manager)
        body = {
            'member_id': (member or self.alice_member).id,
            'date': self.today,
            'time': '16:31',
            'items': items if items is not None else [{'product': 'Rice', 'price': '700'}, {'product': 'Oil', 'price': '220.50'}],
            **extra,
        }
        return self.client.post('/api/v1/admin/costs', body, format='json')

    def test_manager_adds_a_cost_with_products(self):
        response = self.add(note='Weekly bazar')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['member_name'], 'Alice')
        self.assertEqual(response.data['time'], '16:31')
        self.assertEqual(response.data['total'], 920.5)
        self.assertEqual([i['product'] for i in response.data['items']], ['Rice', 'Oil'])
        self.assertEqual(response.data['recorded_by'], 'Manager Mia')

    def test_specific_validation_errors(self):
        self.assertEqual(str(self.add(items=[]).data['items'][0]), 'Add at least one product with a price.')
        self.assertEqual(str(self.add(items=[{'product': 'Rice', 'price': '0'}]).data['items'][0]['price'][0]), 'Price must be greater than 0.')
        self.assertEqual(str(self.add(items=[{'product': '  ', 'price': '10'}]).data['items'][0]['product'][0]), 'This field may not be blank.')
        self.assertIn('before the season started', str(self.add(date='01-01-2000').data['date']))
        outsider = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.client.force_authenticate(user=outsider)
        self.client.post('/api/v1/user/messes/create', {'name': 'Other', 'season_name': 'S1'}, format='json')
        bob_member = MessMemberShip.objects.get(user=outsider)
        self.assertEqual(str(self.add(member=bob_member).data['member_id']), 'Member is not part of the current season.')

    def test_members_read_the_season_list_but_cannot_change_it(self):
        cost_id = self.add().data['id']
        self.add(items=[{'product': 'Fish', 'price': '600'}], member=self.manager_member)
        self.client.force_authenticate(user=self.alice)

        listing = self.client.get('/api/v1/user/costs')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['season']['name'], 'July 2026')
        self.assertEqual(listing.data['summary'], {'total': 1520.5, 'entries': 2, 'items': 3})
        self.assertEqual(len(listing.data['data']), 2)

        self.assertEqual(self.client.post('/api/v1/admin/costs', {}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/admin/costs/{cost_id}', {'note': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/v1/admin/costs/{cost_id}').status_code, 403)

    def test_update_replaces_products_and_total(self):
        cost_id = self.add().data['id']
        response = self.client.patch(
            f'/api/v1/admin/costs/{cost_id}',
            {'member_id': self.manager_member.id, 'time': '09:05', 'items': [{'product': 'Eggs', 'price': '150'}]},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['member_name'], 'Manager Mia')
        self.assertEqual(response.data['time'], '09:05')
        self.assertEqual(response.data['total'], 150.0)
        self.assertEqual([i['product'] for i in response.data['items']], ['Eggs'])
        self.assertEqual(CostBreakdown.objects.count(), 1)

        missing_price = self.client.patch(f'/api/v1/admin/costs/{cost_id}', {'items': [{'product': 'Salt'}]}, format='json')
        self.assertEqual(missing_price.status_code, 400)
        self.assertEqual(Cost.objects.get().amount, 150)

    def test_delete_and_not_found(self):
        cost_id = self.add().data['id']
        self.assertEqual(self.client.delete(f'/api/v1/admin/costs/{cost_id}').status_code, 200)
        self.assertFalse(CostBreakdown.objects.exists())
        response = self.client.delete(f'/api/v1/admin/costs/{cost_id}')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(str(response.data['detail']), 'Cost entry not found in the current season.')

    def test_new_season_starts_with_an_empty_cost_list(self):
        self.add()
        august = self.client.post('/api/v1/admin/seasons', {'name': 'August 2026'}, format='json').data['season']
        self.client.post(f"/api/v1/admin/seasons/{august['id']}/switch")
        listing = self.client.get('/api/v1/user/costs').data
        self.assertEqual(listing['season']['name'], 'August 2026')
        self.assertEqual(listing['data'], [])
        self.assertEqual(listing['summary'], {'total': 0.0, 'entries': 0, 'items': 0})

    def test_user_without_a_mess_gets_a_specific_error(self):
        loner = User.objects.create_user(email='lone@test.com', phone='01744444444', full_name='Lone', password='pass12345')
        self.client.force_authenticate(user=loner)
        response = self.client.get('/api/v1/user/costs')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(str(response.data['detail']), 'You are not connected to an active mess.')

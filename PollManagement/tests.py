from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from AuthManagement.models import User
from MessManagement.models import Mess, MessMemberShip, MessSeason
from .models import Poll, PollOption, PollVote
from .serializers import local_today


class PollApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.mess = Mess.objects.create(name='Poll Mess', email='poll@test.com', phone='0170000000')
        self.season = MessSeason.objects.create(
            mess=self.mess, name='Season 1', start_date=local_today() - timedelta(days=30),
        )
        self.manager_user = User.objects.create_user(
            email='manager@poll.com', phone='0171111111', full_name='Poll Manager', password='pass12345',
        )
        self.member_user = User.objects.create_user(
            email='member@poll.com', phone='0172222222', full_name='Poll Member', password='pass12345',
        )
        self.mess.manager = self.manager_user
        self.mess.save(update_fields=['manager'])
        self.manager = MessMemberShip.objects.create(
            user=self.manager_user, mess=self.mess, season=self.season, status='active',
        )
        self.member = MessMemberShip.objects.create(
            user=self.member_user, mess=self.mess, season=self.season, status='active',
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def create_poll(self, **overrides):
        payload = {
            'title': 'Friday dinner',
            'description': 'Choose one',
            'poll_date': local_today().isoformat(),
            'options': ['Beef', 'Chicken'],
            **overrides,
        }
        self.auth(self.manager_user)
        return self.client.post('/api/v1/admin/polls', payload, format='json')

    # -- create / permissions ---------------------------------------------

    def test_manager_creates_poll_and_member_can_read_it(self):
        response = self.create_poll()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'open')
        self.assertEqual(len(response.data['options']), 2)
        self.assertTrue(response.data['can_manage'])

        self.auth(self.member_user)
        listing = self.client.get('/api/v1/user/polls')
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(len(listing.data['data']), 1)
        self.assertFalse(listing.data['data'][0]['can_manage'])
        self.assertFalse(listing.data['data'][0]['has_voted'])

    def test_plain_member_cannot_create_poll(self):
        self.auth(self.member_user)
        response = self.client.post('/api/v1/admin/polls', {
            'title': 'Nope', 'poll_date': local_today().isoformat(), 'options': ['A', 'B'],
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_options_are_validated(self):
        duplicate = self.create_poll(options=['Beef', 'beef'])
        self.assertEqual(duplicate.status_code, 400)
        single = self.create_poll(options=['Only'])
        self.assertEqual(single.status_code, 400)

    def test_poll_date_cannot_be_in_the_past(self):
        response = self.create_poll(poll_date=(local_today() - timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 400)
        self.assertIn('poll_date', response.data)

    def test_poll_date_must_be_inside_the_season(self):
        self.season.end_date = local_today() - timedelta(days=1)
        self.season.save(update_fields=['end_date'])
        response = self.create_poll()
        self.assertEqual(response.status_code, 400)
        self.assertIn('poll_date', response.data)

    # -- nearest date ordering --------------------------------------------

    def test_polls_are_sorted_nearest_date_first(self):
        self.create_poll(title='Later', poll_date=(local_today() + timedelta(days=3)).isoformat())
        self.create_poll(title='Nearest', poll_date=(local_today() + timedelta(days=1)).isoformat())
        self.create_poll(title='Today', poll_date=local_today().isoformat())

        self.auth(self.member_user)
        response = self.client.get('/api/v1/user/polls')
        titles = [item['title'] for item in response.data['data']]
        self.assertEqual(titles, ['Today', 'Nearest', 'Later'])

    # -- voting ------------------------------------------------------------

    def test_member_votes_and_changes_choice(self):
        poll = self.create_poll().data
        option_a, option_b = poll['options'][0]['id'], poll['options'][1]['id']

        self.auth(self.member_user)
        first = self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': [option_a]}, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertTrue(first.data['has_voted'])
        self.assertEqual(first.data['my_option_ids'], [option_a])
        self.assertEqual(first.data['total_votes'], 1)
        self.assertTrue(first.data['results_visible'])

        second = self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': [option_b]}, format='json')
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['my_option_ids'], [option_b])
        self.assertEqual(PollVote.objects.filter(poll_id=poll['id']).count(), 1)

    def test_single_choice_rejects_two_options(self):
        poll = self.create_poll().data
        ids = [option['id'] for option in poll['options']]
        self.auth(self.member_user)
        response = self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': ids}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_multiple_choice_enforces_max_choices(self):
        poll = self.create_poll(allow_multiple=True, max_choices=2, options=['A', 'B', 'C']).data
        ids = [option['id'] for option in poll['options']]
        self.auth(self.member_user)
        too_many = self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': ids}, format='json')
        self.assertEqual(too_many.status_code, 400)
        ok = self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': ids[:2]}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(len(ok.data['my_option_ids']), 2)

    def test_closed_poll_rejects_votes(self):
        poll = self.create_poll().data
        self.auth(self.manager_user)
        closed = self.client.post(f"/api/v1/admin/polls/{poll['id']}/close", {'closed': True}, format='json')
        self.assertEqual(closed.status_code, 200, closed.data)
        self.assertEqual(closed.data['status'], 'closed')

        self.auth(self.member_user)
        response = self.client.post(
            f"/api/v1/user/polls/{poll['id']}/vote",
            {'option_ids': [poll['options'][0]['id']]}, format='json',
        )
        self.assertEqual(response.status_code, 409)

    def test_results_hidden_before_vote(self):
        poll = self.create_poll(results_visibility='after_vote').data
        self.auth(self.member_user)
        response = self.client.get('/api/v1/user/polls')
        item = response.data['data'][0]
        self.assertFalse(item['results_visible'])
        self.assertIsNone(item['options'][0]['vote_count'])

        self.auth(self.manager_user)
        managed = self.client.get('/api/v1/admin/polls')
        self.assertTrue(managed.data['data'][0]['results_visible'])

    # -- manage ------------------------------------------------------------

    def test_options_are_locked_after_votes(self):
        poll = self.create_poll().data
        self.auth(self.member_user)
        self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': [poll['options'][0]['id']]}, format='json')

        self.auth(self.manager_user)
        response = self.client.patch(
            f"/api/v1/admin/polls/{poll['id']}", {'options': ['A', 'B']}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_without_votes_removes_poll(self):
        poll = self.create_poll().data
        self.auth(self.manager_user)
        response = self.client.delete(f"/api/v1/admin/polls/{poll['id']}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(Poll.objects.filter(pk=poll['id']).exists())

    def test_delete_with_votes_cancels_and_hides_from_members(self):
        poll = self.create_poll().data
        self.auth(self.member_user)
        self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': [poll['options'][0]['id']]}, format='json')

        self.auth(self.manager_user)
        response = self.client.delete(f"/api/v1/admin/polls/{poll['id']}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'cancelled')
        self.assertTrue(Poll.objects.filter(pk=poll['id']).exists())

        self.auth(self.member_user)
        listing = self.client.get('/api/v1/user/polls')
        self.assertEqual(listing.data['data'], [])

    def test_results_are_hidden_for_anonymous_polls(self):
        poll = self.create_poll().data
        self.auth(self.member_user)
        self.client.post(f"/api/v1/user/polls/{poll['id']}/vote", {'option_ids': [poll['options'][0]['id']]}, format='json')

        self.auth(self.manager_user)
        response = self.client.get(f"/api/v1/admin/polls/{poll['id']}/results")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_votes'], 1)
        self.assertEqual(response.data['voters'], [])

    def test_poll_date_cannot_be_changed(self):
        poll = self.create_poll().data
        self.auth(self.manager_user)
        response = self.client.patch(
            f"/api/v1/admin/polls/{poll['id']}",
            {'poll_date': (local_today() + timedelta(days=1)).isoformat()},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

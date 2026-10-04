from datetime import date

from rest_framework.test import APITestCase

from AuthManagement.models import User
from .models import MessMemberShip, MessMemberShipRequest, MessSeason


class InviteAndJoinRequestSeasonTests(APITestCase):
    """The manager chooses which running season an invited or approved user joins."""

    def setUp(self):
        self.mia = User.objects.create_user(email='mia@test.com', phone='01711111111', full_name='Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01733333333', full_name='Alice', password='pass12345')
        self.as_user(self.mia)
        response = self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July 2026'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.mess_id = response.data['current']['mess_id']
        self.july = MessSeason.objects.get(pk=response.data['current']['season_id'])
        self.august = MessSeason.objects.create(mess_id=self.mess_id, name='August 2026', start_date=date(2026, 8, 1))

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def invite(self, **data):
        self.as_user(self.mia)
        return self.client.post('/api/v1/admin/invites', {'user_id': self.alice.id, **data}, format='json')

    def accept(self, code):
        self.as_user(self.alice)
        return self.client.post('/api/v1/user/invites/accept', {'invite_code': code}, format='json')

    def request_to_join(self):
        self.as_user(self.alice)
        response = self.client.post('/api/v1/user/join-requests', {'mess_id': self.mess_id}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def decide(self, request_id, decision='accepted', **data):
        self.as_user(self.mia)
        return self.client.post('/api/v1/admin/join-requests/decision', {'request_id': request_id, 'decision': decision, **data}, format='json')

    def create_other_mess(self):
        bob = User.objects.create_user(email='bob@test.com', phone='01722222222', full_name='Bob', password='pass12345')
        self.as_user(bob)
        return self.client.post('/api/v1/user/messes/create', {'name': 'Blue House', 'season_name': 'July 2026'}, format='json').data['current']['mess_id']

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))

    # -- invites ---------------------------------------------------------------

    def test_invite_joins_the_chosen_season(self):
        invite = self.invite(season_id=self.august.id)
        self.assertEqual(invite.status_code, 201, invite.data)
        self.assertEqual((invite.data['season_id'], invite.data['season_name']), (self.august.id, 'August 2026'))

        self.as_user(self.alice)
        listed = self.client.get('/api/v1/user/membership/status').data['invites'][0]
        self.assertEqual(listed['season_name'], 'August 2026')

        accepted = self.accept(invite.data['invite_code'])
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data['current']['season_name'], 'August 2026')
        self.assertEqual(list(MessMemberShip.objects.filter(user=self.alice).values_list('season__name', flat=True)), ['August 2026'])

    def test_invite_without_season_uses_the_managers_season(self):
        invite = self.invite()
        self.assertEqual(invite.data['season_name'], 'July 2026')

    def test_invite_refuses_seasons_that_are_not_running(self):
        ended = MessSeason.objects.create(mess_id=self.mess_id, name='June 2026', start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        disabled = MessSeason.objects.create(mess_id=self.mess_id, name='May 2026', start_date=date(2026, 5, 1), is_disabled=True)
        other = MessSeason.objects.create(mess_id=self.create_other_mess(), name='Other', start_date=date(2026, 7, 1))

        self.assertRejected(self.invite(season_id=ended.id), 'June 2026 has ended. Choose a running season.')
        self.assertRejected(self.invite(season_id=disabled.id), 'May 2026 is disabled. Choose a running season.')
        self.assertRejected(self.invite(season_id=other.id), 'Season not found in this mess.')
        self.assertRejected(self.invite(season_id='abc'), 'season_id must be a number.')

    def test_a_member_of_one_season_can_be_invited_to_another(self):
        self.accept(self.invite(season_id=self.july.id).data['invite_code'])
        self.assertRejected(self.invite(season_id=self.july.id), 'Alice is already a member of July 2026.')

        lookup = self.client.get('/api/v1/admin/member-lookup', {'query': 'alice@test.com'}).data
        self.assertEqual((lookup['available'], lookup['joined_season_ids']), (True, [self.july.id]))

        self.assertEqual(self.invite(season_id=self.august.id).status_code, 201)

    def test_invite_for_a_season_that_ended_since_cannot_be_accepted(self):
        code = self.invite(season_id=self.august.id).data['invite_code']
        self.august.end_date = date(2026, 8, 31)
        self.august.save(update_fields=['end_date'])
        self.assertRejected(self.accept(code), 'August 2026 has ended. Ask the manager for a new invite.')

    # -- join requests ---------------------------------------------------------

    def test_approving_a_request_adds_the_user_to_the_chosen_season(self):
        request_id = self.request_to_join()
        decision = self.decide(request_id, season_id=self.august.id)
        self.assertEqual(decision.status_code, 200, decision.data)
        self.assertEqual(decision.data['message'], 'Alice joined August 2026.')

        self.assertEqual(MessMemberShipRequest.objects.get(pk=request_id).season, self.august)
        self.assertEqual(list(MessMemberShip.objects.filter(user=self.alice).values_list('season__name', flat=True)), ['August 2026'])
        listed = self.client.get('/api/v1/admin/join-requests').data[0]
        self.assertEqual((listed['status'], listed['season_name']), ('approved', 'August 2026'))
        self.as_user(self.alice)
        self.assertEqual(self.client.get('/api/v1/user/membership/status').data['join_requests'][0]['season_name'], 'August 2026')

    def test_approving_into_a_closed_or_joined_season_is_refused(self):
        self.august.is_disabled = True
        self.august.save(update_fields=['is_disabled'])
        request_id = self.request_to_join()
        self.assertRejected(self.decide(request_id, season_id=self.august.id), 'August 2026 is disabled. Choose a running season.')

        MessMemberShip.objects.create(user=self.alice, mess_id=self.mess_id, season=self.july)
        self.assertRejected(self.decide(request_id, season_id=self.july.id), 'Alice is already a member of July 2026.')
        self.assertEqual(MessMemberShipRequest.objects.get(pk=request_id).status, 'pending')

    def test_rejecting_needs_no_season(self):
        request_id = self.request_to_join()
        decision = self.decide(request_id, decision='rejected')
        self.assertEqual(decision.status_code, 200, decision.data)
        self.assertIsNone(MessMemberShipRequest.objects.get(pk=request_id).season)

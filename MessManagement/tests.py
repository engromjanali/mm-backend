from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from AuthManagement.authentication import create_access_token
from .models import Mess, MessMemberShip, MessSeason

User = get_user_model()


class StartNewSeasonTests(APITestCase):
    url = '/api/v1/season/start-new-season'

    def setUp(self):
        self.manager = User.objects.create_user(
            email='manager@example.com', phone='0100000001', full_name='Manager', password='pass12345'
        )
        self.member = User.objects.create_user(
            email='member@example.com', phone='0100000002', full_name='Member', password='pass12345'
        )
        self.leaver = User.objects.create_user(
            email='leaver@example.com', phone='0100000003', full_name='Leaver', password='pass12345'
        )

        self.mess = Mess.objects.create(
            name='Test Mess', email='mess@example.com', phone='0100000000', address='Dhaka'
        )
        self.season = MessSeason.objects.create(
            mess=self.mess, name='Season 1', start_date=timezone.now().date()
        )

        self.manager_membership = MessMemberShip.objects.create(
            user=self.manager, mess=self.mess, season=self.season, role='manager', status='active'
        )
        self.member_membership = MessMemberShip.objects.create(
            user=self.member, mess=self.mess, season=self.season, role='member', status='active'
        )
        # This one left the mess and must not be migrated.
        MessMemberShip.objects.create(
            user=self.leaver, mess=self.mess, season=self.season, role='member',
            status='inactive', left_at=timezone.now(),
        )

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(user)}')

    def post(self, user, season_id, membership_id, data=None):
        self.auth(user)
        return self.client.post(
            self.url,
            data or {},
            format='json',
            HTTP_SEASON_ID=str(season_id),
            HTTP_MEMBERSHIP_ID=str(membership_id),
        )

    def test_manager_starts_new_season_and_migrates_active_members(self):
        response = self.post(self.manager, self.season.pk, self.manager_membership.pk)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['migrated_members_count'], 2)

        new_season = MessSeason.objects.get(pk=response.data['season']['id'])
        self.assertEqual(new_season.name, 'Season 2')
        self.assertTrue(new_season.is_active)
        self.assertIsNone(new_season.end_date)

        self.season.refresh_from_db()
        self.assertFalse(self.season.is_active)
        self.assertEqual(self.season.end_date, new_season.start_date)

        migrated = MessMemberShip.objects.filter(season=new_season)
        self.assertEqual(
            sorted(migrated.values_list('user__email', 'role')),
            [('manager@example.com', 'manager'), ('member@example.com', 'member')],
        )
        self.assertFalse(migrated.filter(user=self.leaver).exists())

    def test_custom_name_and_start_date_are_honoured(self):
        response = self.post(
            self.manager, self.season.pk, self.manager_membership.pk,
            {'name': 'Winter 2026', 'start_date': '2026-12-01'},
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['season']['name'], 'Winter 2026')
        self.assertEqual(response.data['season']['start_date'], '2026-12-01')

    def test_member_cannot_start_a_new_season(self):
        response = self.post(self.member, self.season.pk, self.member_membership.pk)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MessSeason.objects.filter(mess=self.mess).count(), 1)

    def test_membership_of_another_user_is_rejected(self):
        response = self.post(self.member, self.season.pk, self.manager_membership.pk)
        self.assertEqual(response.status_code, 403)

    def test_season_header_must_match_the_membership(self):
        other_season = MessSeason.objects.create(
            mess=self.mess, name='Other', start_date=timezone.now().date()
        )
        response = self.post(self.manager, other_season.pk, self.manager_membership.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn('season_id', response.data)

    def test_stale_season_is_rejected(self):
        # A newer season exists, so the manager's season is no longer the latest.
        newer = MessSeason.objects.create(
            mess=self.mess, name='Season 2', start_date=timezone.now().date()
        )
        newer_membership = MessMemberShip.objects.create(
            user=self.manager, mess=self.mess, season=newer, role='manager', status='active'
        )
        response = self.post(self.manager, self.season.pk, self.manager_membership.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn('season_id', response.data)

        # The membership on the latest season works.
        response = self.post(self.manager, newer.pk, newer_membership.pk)
        self.assertEqual(response.status_code, 201, response.data)

    def test_missing_headers_are_rejected(self):
        self.auth(self.manager)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('season_id', response.data)

    def test_authentication_is_required(self):
        self.client.credentials()
        response = self.client.post(
            self.url, {}, format='json',
            HTTP_SEASON_ID=str(self.season.pk),
            HTTP_MEMBERSHIP_ID=str(self.manager_membership.pk),
        )
        self.assertEqual(response.status_code, 401)

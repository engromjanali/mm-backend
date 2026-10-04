from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from AuthManagement.models import User
from DepositManagement.models import Deposit
from .models import Mess, MessMemberShip, MessSeason
from .utils import auto_create_due, mess_today, run_auto_create_seasons


class SeasonManagementAPITests(APITestCase):
    """Several seasons run at once; the manager creates, switches, ends, disables and deletes them."""

    def setUp(self):
        self.manager = User.objects.create_user(email='manager@test.com', phone='01711111111', full_name='Manager Mia', password='pass12345')
        self.alice = User.objects.create_user(email='alice@test.com', phone='01722222222', full_name='Alice', password='pass12345')
        self.bob = User.objects.create_user(email='bob@test.com', phone='01733333333', full_name='Bob', password='pass12345')
        self.as_user(self.manager)
        self.client.post('/api/v1/user/messes/create', {'name': 'Green House', 'season_name': 'July'}, format='json')
        self.mess = Mess.objects.get()
        self.july = self.mess.active_season
        for user in (self.alice, self.bob):
            self.as_user(self.manager)
            code = self.client.post('/api/v1/admin/invites', {'user_id': user.id}, format='json').data['invite_code']
            self.as_user(user)
            self.client.post('/api/v1/user/invites/accept', {'invite_code': code}, format='json')
        self.as_user(self.manager)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def create_season(self, name, **extra):
        response = self.client.post('/api/v1/admin/seasons', {'name': name, **extra}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return MessSeason.objects.get(pk=response.data['season']['id'])

    def members_of(self, season):
        return set(MessMemberShip.objects.filter(season=season).values_list('user__email', flat=True))

    def current_season_id(self, user):
        user.refresh_from_db()
        return user.current_membership.season_id if user.current_membership else None

    def assertRejected(self, response, text, status_code=400):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(text, str(response.data))

    # -- create ---------------------------------------------------------------

    def test_new_season_copies_members_who_did_not_leave_and_ends_nothing(self):
        self.as_user(self.bob)
        self.client.post('/api/v1/user/membership/leave')
        self.as_user(self.manager)
        alice = MessMemberShip.objects.get(season=self.july, user=self.alice)
        alice.status = 'inactive'
        alice.save()

        august = self.create_season('August')

        self.assertEqual(self.members_of(august), {'manager@test.com', 'alice@test.com'})
        # A disabled member stays disabled in the new season.
        self.assertEqual(MessMemberShip.objects.get(season=august, user=self.alice).status, 'inactive')
        self.july.refresh_from_db()
        self.assertEqual(self.july.status, 'running')
        # Nobody switches automatically.
        self.assertEqual(self.current_season_id(self.manager), self.july.id)

    def test_new_season_copies_members_from_the_mentioned_season(self):
        august = self.create_season('August')
        MessMemberShip.objects.filter(season=august, user=self.bob).update(left_at=timezone.now(), status='inactive')

        september = self.create_season('September', source_season_id=august.id)

        self.assertEqual(self.members_of(september), {'manager@test.com', 'alice@test.com'})

    def test_create_rejects_duplicate_name_and_foreign_source(self):
        self.assertRejected(self.client.post('/api/v1/admin/seasons', {'name': 'july'}, format='json'), 'This mess already has a season named july.')
        self.assertRejected(self.client.post('/api/v1/admin/seasons', {'name': ''}, format='json'), 'Season name is required.')
        other = Mess.objects.create(name='Other')
        foreign = MessSeason.objects.create(mess=other, name='X', start_date=date(2026, 1, 1))
        self.assertRejected(
            self.client.post('/api/v1/admin/seasons', {'name': 'August', 'source_season_id': foreign.id}, format='json'),
            "That season isn't in this mess.",
        )

    def test_members_cannot_manage_seasons(self):
        self.as_user(self.alice)
        self.assertRejected(self.client.get('/api/v1/admin/seasons'), 'Only the manager or acting manager can do this.', 403)

    # -- list -----------------------------------------------------------------

    def test_list_shows_every_season_with_status_and_the_one_in_use(self):
        august = self.create_season('August')
        data = self.client.get('/api/v1/admin/seasons').data

        self.assertEqual(data['current_season_id'], self.july.id)
        self.assertEqual(data['auto_create'], {'enabled': False, 'day': 0})
        listed = {s['name']: (s['status'], s['member_count'], s['is_current']) for s in data['seasons']}
        self.assertEqual(listed, {'July': ('running', 3, True), 'August': ('running', 3, False)})
        self.assertEqual(august.status, 'running')

    # -- switch ---------------------------------------------------------------

    def test_manager_switches_the_season_they_work_in(self):
        august = self.create_season('August')
        response = self.client.post(f'/api/v1/admin/seasons/{august.id}/switch')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.current_season_id(self.manager), august.id)
        self.assertEqual(self.client.get('/api/v1/user/membership/status').data['current']['season_name'], 'August')
        # Members keep working in their own season.
        self.assertEqual(self.current_season_id(self.alice), self.july.id)
        self.assertRejected(self.client.post(f'/api/v1/admin/seasons/{august.id}/switch'), "You're already working in August.")

    def test_cannot_switch_to_a_disabled_season(self):
        august = self.create_season('August')
        self.client.post(f'/api/v1/admin/seasons/{august.id}/disable')
        self.assertRejected(self.client.post(f'/api/v1/admin/seasons/{august.id}/switch'), 'August is disabled. Enable it before switching to it.')

        self.as_user(self.alice)
        membership = MessMemberShip.objects.get(season=august, user=self.alice)
        self.assertRejected(
            self.client.post('/api/v1/user/membership/switch', {'membership_id': membership.id}, format='json'),
            "Green House (August) is disabled by its manager",
        )

    # -- edit / end -------------------------------------------------------------

    def test_edit_renames_and_moves_dates(self):
        response = self.client.patch(f'/api/v1/admin/seasons/{self.july.id}', {'name': 'July 2026', 'start_date': '2026-07-01', 'end_date': '31-07-2026'}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.july.refresh_from_db()
        self.assertEqual((self.july.name, self.july.start_date, self.july.end_date), ('July 2026', date(2026, 7, 1), date(2026, 7, 31)))
        self.assertEqual(self.july.status, 'ended')

        # end_date: null reopens it.
        self.client.patch(f'/api/v1/admin/seasons/{self.july.id}', {'end_date': None}, format='json')
        self.july.refresh_from_db()
        self.assertEqual(self.july.status, 'running')

    def test_edit_rejects_dates_that_leave_records_outside_the_season(self):
        self.client.patch(f'/api/v1/admin/seasons/{self.july.id}', {'start_date': '2026-07-01'}, format='json')
        manager = MessMemberShip.objects.get(season=self.july, user=self.manager)
        Deposit.objects.create(season=self.july, performed_by=manager, date=date(2026, 7, 20), amount=500)

        self.assertRejected(
            self.client.patch(f'/api/v1/admin/seasons/{self.july.id}', {'end_date': '2026-07-10'}, format='json'),
            "July has records up to 20-07-2026, so it can't end before that.",
        )
        self.assertRejected(
            self.client.patch(f'/api/v1/admin/seasons/{self.july.id}', {'start_date': '2026-07-25'}, format='json'),
            "July has records from 20-07-2026, so it can't start later than that.",
        )
        self.assertRejected(
            self.client.patch(f'/api/v1/admin/seasons/{self.july.id}', {'end_date': '2026-06-01'}, format='json'),
            "The end date can't be before the start date.",
        )

    def test_end_closes_a_running_season_today(self):
        response = self.client.post(f'/api/v1/admin/seasons/{self.july.id}/end')

        self.assertEqual(response.status_code, 200, response.data)
        self.july.refresh_from_db()
        self.assertEqual(self.july.end_date, timezone.localdate())
        self.assertRejected(self.client.post(f'/api/v1/admin/seasons/{self.july.id}/end'), 'July already ended on')

    # -- disable / enable -------------------------------------------------------

    def test_disable_moves_members_working_in_it_and_enable_restores_it(self):
        august = self.create_season('August')
        self.as_user(self.alice)
        self.client.post('/api/v1/user/membership/switch', {'membership_id': MessMemberShip.objects.get(season=august, user=self.alice).id}, format='json')

        self.as_user(self.manager)
        response = self.client.post(f'/api/v1/admin/seasons/{august.id}/disable')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.current_season_id(self.alice), self.july.id)
        self.assertRejected(self.client.post(f'/api/v1/admin/seasons/{august.id}/disable'), 'August is already disabled.')
        self.assertEqual(self.client.post(f'/api/v1/admin/seasons/{august.id}/enable').status_code, 200)
        august.refresh_from_db()
        self.assertEqual(august.status, 'running')

    def test_cannot_disable_the_season_you_work_in(self):
        self.assertRejected(
            self.client.post(f'/api/v1/admin/seasons/{self.july.id}/disable'),
            "You're working in July. Switch to another season before disabling it.",
        )

    # -- delete -----------------------------------------------------------------

    def test_delete_removes_the_season_with_its_data_and_moves_its_members(self):
        august = self.create_season('August')
        self.client.post(f'/api/v1/admin/seasons/{august.id}/switch')
        member = MessMemberShip.objects.get(season=august, user=self.manager)
        Deposit.objects.create(season=august, performed_by=member, date=timezone.localdate(), amount=300)

        response = self.client.delete(f'/api/v1/admin/seasons/{august.id}')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['current_season_id'], self.july.id)
        self.assertFalse(MessSeason.objects.filter(pk=august.id).exists())
        self.assertFalse(Deposit.objects.filter(season_id=august.id).exists())
        self.assertEqual(self.current_season_id(self.manager), self.july.id)

    def test_cannot_delete_the_only_season_you_can_work_in(self):
        self.assertRejected(
            self.client.delete(f'/api/v1/admin/seasons/{self.july.id}'),
            'July is the only season you can work in. Create or enable another season before deleting it.',
        )

    # -- auto-create ------------------------------------------------------------

    def test_auto_create_setting_is_saved_and_validated(self):
        response = self.client.put('/api/v1/admin/seasons/auto-create', {'enabled': True, 'day': 15}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['auto_create'], {'enabled': True, 'day': 15})
        self.assertIn('on day 15 of every month', response.data['message'])
        self.assertRejected(
            self.client.put('/api/v1/admin/seasons/auto-create', {'day': 31}, format='json'),
            'Choose a day from 1 to 28, or 0 for the last day of the month.',
        )

    def test_auto_create_is_due_on_its_day_or_the_last_day_of_the_month(self):
        self.mess.auto_create_season = True
        self.mess.auto_create_season_day = 0
        self.assertTrue(auto_create_due(self.mess, date(2028, 2, 29)))
        self.assertFalse(auto_create_due(self.mess, date(2028, 2, 28)))
        self.assertTrue(auto_create_due(self.mess, date(2026, 4, 30)))
        self.mess.auto_create_season_day = 15
        self.assertTrue(auto_create_due(self.mess, date(2026, 4, 15)))
        self.assertFalse(auto_create_due(self.mess, date(2026, 4, 16)))
        self.mess.last_auto_season_on = date(2026, 4, 15)
        self.assertFalse(auto_create_due(self.mess, date(2026, 4, 15)))

    def test_auto_create_starts_a_season_from_the_active_one_and_switches_its_members(self):
        self.as_user(self.bob)
        self.client.post('/api/v1/user/membership/leave')
        Mess.objects.filter(pk=self.mess.pk).update(auto_create_season=True, auto_create_season_day=10)
        today = date(2026, 8, 10)

        created = run_auto_create_seasons(today)

        self.assertEqual(len(created), 1)
        season = created[0]
        self.assertRegex(season.name, r'^season-[a-z]{3}$')
        self.assertEqual(season.start_date, today)
        self.assertEqual(self.members_of(season), {'manager@test.com', 'alice@test.com'})
        self.assertEqual(self.current_season_id(self.manager), season.id)
        self.assertEqual(self.current_season_id(self.alice), season.id)
        self.july.refresh_from_db()
        self.assertEqual(self.july.status, 'running')
        # Runs once per day.
        self.assertEqual(run_auto_create_seasons(today), [])
        self.assertEqual(run_auto_create_seasons(today + timedelta(days=1)), [])

    # -- nightly trigger ----------------------------------------------------------

    @override_settings(CRON_SECRET='s3cret')
    def test_cron_endpoint_creates_due_seasons_once(self):
        Mess.objects.filter(pk=self.mess.pk).update(auto_create_season=True, auto_create_season_day=10)
        url = '/api/v1/cron/create-scheduled-seasons'
        self.assertRejected(self.client.get(url, HTTP_AUTHORIZATION='Bearer wrong'), 'Invalid cron secret.', 403)

        with mock.patch('MessManagement.cron_views.mess_today', return_value=date(2026, 8, 10)):
            response = self.client.get(url, HTTP_AUTHORIZATION='Bearer s3cret')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['message'], '1 season(s) created.')
            self.assertRegex(response.data['seasons'][0]['season_name'], r'^season-[a-z]{3}$')
            # A repeated call the same day creates nothing.
            self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION='Bearer s3cret').data['message'], '0 season(s) created.')

    @override_settings(MESS_TIME_ZONE='Asia/Dhaka')
    def test_jobs_use_the_bangladesh_date_not_utc(self):
        # 19:00 UTC on 9 Aug is 1:00 AM on 10 Aug in Bangladesh.
        with mock.patch('django.utils.timezone.now', return_value=datetime(2026, 8, 9, 19, 0, tzinfo=dt_timezone.utc)):
            self.assertEqual(mess_today(), date(2026, 8, 10))

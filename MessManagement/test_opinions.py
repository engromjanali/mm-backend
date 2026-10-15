from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from AuthManagement.models import User
from MessManagement.models import AnonymousOpinion, Mess, MessMemberShip, MessSeason, OpinionPeriod


class OpinionAPITests(APITestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.manager = self.user('manager', '01711111111')
        self.member = self.user('member', '01722222222')
        self.old_member = self.user('old', '01733333333')
        self.outsider = self.user('outsider', '01744444444')
        self.mess = Mess.objects.create(name='Green House', manager=self.manager)
        self.old_season = MessSeason.objects.create(mess=self.mess, name='Old season', start_date=self.today - timedelta(days=30), end_date=self.today - timedelta(days=1))
        self.season = MessSeason.objects.create(mess=self.mess, name='Current season', start_date=self.today)
        for user in (self.manager, self.member):
            membership = MessMemberShip.objects.create(user=user, mess=self.mess, season=self.season)
            user.current_membership = membership
            user.save(update_fields=['current_membership'])
        MessMemberShip.objects.create(user=self.old_member, mess=self.mess, season=self.old_season)
        self.period = OpinionPeriod.objects.create(season=self.season, title='Feedback', details='Share feedback', start_date=self.today, end_date=self.today + timedelta(days=7))
        self.client.force_authenticate(user=self.member)

    def user(self, name, phone):
        return User.objects.create_user(email=f'{name}@test.com', phone=phone, full_name=name, password='pass12345')

    def messages(self, period=None, **kwargs):
        return self.client.get(f'/api/v1/user/opinions/{(period or self.period).id}/messages', {'mess_id': self.mess.id, **kwargs})

    def submit(self, message='Feedback', period=None):
        return self.client.post(f'/api/v1/user/opinions/{(period or self.period).id}/messages', {'message': message}, format='json')

    def publish(self):
        return self.client.post(f'/api/v1/admin/opinions/{self.period.id}/publish')

    def overview(self, **kwargs):
        return self.client.get('/api/v1/user/opinions', {'mess_id': self.mess.id, **kwargs})

    def test_current_members_submit_without_any_stored_author(self):
        self.assertEqual(self.submit('  Honest feedback  ').status_code, 201)
        opinion = AnonymousOpinion.objects.get()
        self.assertEqual(opinion.message, 'Honest feedback')
        self.assertEqual({field.name for field in AnonymousOpinion._meta.fields}, {'id', 'period', 'message', 'is_published', 'created_at'})
        self.assertEqual(self.messages().data['data'], [])
        self.client.force_authenticate(user=self.manager)
        data = self.messages().data['data'][0]
        self.assertEqual(set(data), {'id', 'period_id', 'message', 'created_at', 'is_published'})

    def test_manager_without_season_membership_cannot_submit_as_a_member(self):
        period = OpinionPeriod.objects.create(season=self.old_season, title='Old feedback', details='Historical', start_date=self.today - timedelta(days=30), end_date=self.today + timedelta(days=1))
        self.client.force_authenticate(user=self.manager)
        switched = self.client.post('/api/v1/user/membership/switch', {'mess_id': self.mess.id, 'season_id': self.old_season.id}, format='json')
        self.assertEqual(switched.status_code, 200, switched.data)

        response = self.submit(period=period)

        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(AnonymousOpinion.objects.count(), 0)

    def test_old_disabled_left_and_other_mess_members_cannot_submit(self):
        for user in (self.old_member, self.outsider):
            self.client.force_authenticate(user=user)
            self.assertEqual(self.submit().status_code, 403)
        self.client.force_authenticate(user=self.member)
        membership = MessMemberShip.objects.get(user=self.member, season=self.season)
        membership.status = 'inactive'
        membership.save()
        self.assertEqual(self.submit().status_code, 403)
        membership.status = 'active'
        membership.left_at = timezone.now()
        membership.save()
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(AnonymousOpinion.objects.count(), 0)

    def test_submission_requires_period_to_belong_to_selected_current_season(self):
        newer = MessSeason.objects.create(mess=self.mess, name='New season', start_date=self.today + timedelta(days=1))
        self.assertEqual(self.submit().status_code, 201)
        membership = MessMemberShip.objects.create(user=self.member, mess=self.mess, season=newer)
        self.member.current_membership = membership
        self.member.save(update_fields=['current_membership'])
        self.assertFalse(self.overview().data['data'][0]['can_write'])
        self.assertEqual(self.submit().status_code, 403)
        self.member.current_membership = MessMemberShip.objects.get(user=self.member, season=self.season)
        self.member.save(update_fields=['current_membership'])
        self.assertTrue(self.overview().data['data'][0]['can_write'])
        self.assertEqual(self.submit().status_code, 201)
        self.season.end_date = self.today
        self.season.save()
        self.assertEqual(self.submit().status_code, 201)
        self.season.is_disabled = True
        self.season.save()
        self.assertFalse(self.overview().data['data'][0]['can_write'])
        self.assertEqual(self.submit().status_code, 403)

    def test_former_members_can_read_public_opinions_but_cannot_submit(self):
        self.period.visibility = 'realtime'
        self.period.save()
        self.submit('Public feedback')
        membership = MessMemberShip.objects.get(user=self.old_member, season=self.old_season)
        membership.status = 'inactive'
        membership.left_at = timezone.now()
        membership.save()
        self.old_season.is_disabled = True
        self.old_season.save()
        self.client.force_authenticate(user=self.old_member)
        data = self.overview().data['data'][0]
        self.assertEqual(data['opinion_count'], 1)
        self.assertEqual(data['opinions'][0]['message'], 'Public feedback')
        self.assertFalse(data['can_write'])
        self.assertEqual(self.messages().data['data'][0]['message'], 'Public feedback')
        self.assertEqual(self.submit().status_code, 403)

    def test_creation_uses_selected_season_and_edits_keep_original_season(self):
        self.client.force_authenticate(user=self.manager)
        selected = MessMemberShip.objects.create(user=self.manager, mess=self.mess, season=self.old_season)
        self.manager.current_membership = selected
        self.manager.save(update_fields=['current_membership'])
        self.assertEqual(self.overview().data['current_season_id'], self.old_season.id)
        body = {'title': 'Old season feedback', 'details': 'Details', 'start_date': str(self.today), 'end_date': str(self.today + timedelta(days=7)), 'visibility': 'realtime'}
        response = self.client.post('/api/v1/admin/opinions', body, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        period = OpinionPeriod.objects.get(pk=response.data['id'])
        self.assertEqual(period.season_id, self.old_season.id)
        self.manager.current_membership = MessMemberShip.objects.get(user=self.manager, season=self.season)
        self.manager.save(update_fields=['current_membership'])
        url = f'/api/v1/admin/opinions/{period.id}'
        self.assertEqual(self.client.patch(url, {'title': 'Updated from another season', 'end_date': str(self.today + timedelta(days=10))}, format='json').status_code, 200)
        period.refresh_from_db()
        self.assertEqual(period.season_id, self.old_season.id)
        self.assertEqual(period.title, 'Updated from another season')
        self.assertEqual(self.client.patch(url, {'season_id': self.season.id}, format='json').status_code, 400)
        period.refresh_from_db()
        self.assertEqual(period.season_id, self.old_season.id)
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.submit(period=period).status_code, 403)
        self.assertEqual(self.messages(period).status_code, 200)
        self.client.force_authenticate(user=self.old_member)
        self.assertEqual(self.submit('Original season feedback', period=period).status_code, 201)
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.messages(period).data['data'][0]['message'], 'Original season feedback')
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(self.client.patch(url, {'visibility': 'after_publish'}, format='json').status_code, 200)
        self.assertEqual(len(self.messages(period).data['data']), 1)
        period.refresh_from_db()
        self.assertEqual(period.season_id, self.old_season.id)

    def test_all_season_members_can_read_visible_messages_across_seasons(self):
        self.period.visibility = 'realtime'
        self.period.save()
        self.submit('Current feedback')
        old_period = OpinionPeriod.objects.create(season=self.old_season, title='Old feedback', details='Past', start_date=self.today - timedelta(days=30), end_date=self.today, visibility='realtime')
        AnonymousOpinion.objects.create(period=old_period, message='Old feedback')
        for user in (self.member, self.old_member):
            self.client.force_authenticate(user=user)
            data = self.overview().data['data']
            self.assertEqual({period['season_id'] for period in data}, {self.season.id, self.old_season.id})
            self.assertEqual(len(self.messages().data['data']), 1)
            self.assertEqual(len(self.messages(old_period).data['data']), 1)
        self.assertFalse(next(period for period in data if period['id'] == self.period.id)['can_write'])
        self.assertEqual(self.submit(period=old_period).status_code, 201)
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.submit(period=old_period).status_code, 403)

    def test_manager_can_switch_public_and_private_without_changing_submissions(self):
        self.submit('First')
        self.assertEqual(self.overview().data['data'][0]['opinion_count'], 0)
        self.assertEqual(self.overview().data['data'][0]['opinions'], [])
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(self.overview().data['data'][0]['opinion_count'], 1)
        self.assertEqual(self.publish().data['published_count'], 1)
        self.client.force_authenticate(user=self.member)
        self.submit('Later')
        self.assertEqual({opinion['message'] for opinion in self.messages().data['data']}, {'First', 'Later'})
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(self.client.patch(f'/api/v1/admin/opinions/{self.period.id}', {'visibility': 'after_publish'}, format='json').status_code, 200)
        self.assertEqual(self.overview().data['data'][0]['opinion_count'], 2)
        self.client.force_authenticate(user=self.member)
        data = self.overview().data['data'][0]
        self.assertTrue(data['can_write'])
        self.assertEqual((data['opinions'], data['opinion_count'], data['has_more_opinions']), ([], 0, False))
        self.assertEqual(self.messages().data['data'], [])
        self.assertEqual(self.submit('Still private').status_code, 201)
        self.assertEqual(self.client.patch(f'/api/v1/admin/opinions/{self.period.id}', {'visibility': 'realtime'}, format='json').status_code, 403)
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(self.client.patch(f'/api/v1/admin/opinions/{self.period.id}', {'visibility': 'realtime'}, format='json').status_code, 200)
        self.client.force_authenticate(user=self.old_member)
        self.assertEqual({opinion['message'] for opinion in self.messages().data['data']}, {'First', 'Later', 'Still private'})

    def test_deadline_only_closes_submissions_and_manager_can_change_visibility(self):
        self.submit('Feedback before deadline')
        self.period.start_date = self.today - timedelta(days=7)
        self.period.end_date = self.today - timedelta(days=1)
        self.period.save()
        for visibility in ('realtime', 'after_publish', 'realtime'):
            self.client.force_authenticate(user=self.manager)
            self.assertEqual(self.client.patch(f'/api/v1/admin/opinions/{self.period.id}', {'visibility': visibility}, format='json').status_code, 200)
            self.assertEqual(len(self.messages().data['data']), 1)
            self.client.force_authenticate(user=self.member)
            data = self.overview().data['data'][0]
            self.assertFalse(data['can_write'])
            self.assertEqual(data['opinion_count'], 1 if visibility == 'realtime' else 0)
            self.assertEqual(len(self.messages().data['data']), 1 if visibility == 'realtime' else 0)
            self.assertEqual(self.submit().status_code, 400)

    def test_other_mess_and_unauthenticated_users_cannot_read_or_manage(self):
        other_mess = Mess.objects.create(name='Blue House', manager=self.outsider)
        other_season = MessSeason.objects.create(mess=other_mess, name='Other', start_date=self.today)
        MessMemberShip.objects.create(user=self.outsider, mess=other_mess, season=other_season)
        self.client.force_authenticate(user=self.outsider)
        self.assertEqual(self.overview().status_code, 403)
        self.assertEqual(self.messages().status_code, 403)
        self.assertEqual(self.publish().status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/admin/opinions/{self.period.id}', {'visibility': 'realtime'}, format='json').status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertIn(self.overview().status_code, (401, 403))
        self.assertIn(self.submit().status_code, (401, 403))

    def test_manager_creates_in_current_season_and_members_cannot_manage(self):
        body = {'title': ' New feedback ', 'details': ' Details ', 'start_date': str(self.today), 'end_date': str(self.today), 'visibility': 'realtime'}
        self.assertEqual(self.client.post('/api/v1/admin/opinions', body, format='json').status_code, 403)
        self.assertEqual(self.publish().status_code, 403)
        self.client.force_authenticate(user=self.manager)
        response = self.client.post('/api/v1/admin/opinions', body, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        period = OpinionPeriod.objects.get(pk=response.data['id'])
        self.assertEqual((period.season_id, period.title, period.visibility), (self.season.id, 'New feedback', 'realtime'))
        response = self.client.patch(f'/api/v1/admin/opinions/{period.id}', {'accepting_messages': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.submit(period=period).status_code, 400)

    def test_message_and_period_validation(self):
        for message in (' ', 'x' * 2001):
            self.assertEqual(self.submit(message).status_code, 400)
        self.period.accepting_messages = False
        self.period.save()
        self.assertEqual(self.submit().status_code, 400)
        self.client.force_authenticate(user=self.manager)
        for body in ({'visibility': 'invalid'}, {'end_date': str(self.today - timedelta(days=1))}, {'title': 'x' * 121}):
            self.assertEqual(self.client.patch(f'/api/v1/admin/opinions/{self.period.id}', body, format='json').status_code, 400)
        self.assertEqual(AnonymousOpinion.objects.count(), 0)

    def test_pagination_keeps_all_visible_messages_accessible(self):
        self.period.visibility = 'realtime'
        self.period.save()
        AnonymousOpinion.objects.bulk_create([AnonymousOpinion(period=self.period, message=f'Message {index}') for index in range(25)])
        first = self.overview().data['data'][0]
        self.assertEqual((len(first['opinions']), first['opinion_count'], first['has_more_opinions']), (20, 25, True))
        self.assertEqual((len(self.messages().data['data']), self.messages().data['next_page']), (20, 2))
        self.assertEqual((len(self.messages(page=2).data['data']), self.messages(page=2).data['next_page']), (5, None))
        OpinionPeriod.objects.bulk_create([OpinionPeriod(season=self.season, title=f'Period {index}', details='Details', start_date=self.today, end_date=self.today) for index in range(11)])
        self.assertEqual((len(self.overview().data['data']), self.overview().data['next_page']), (10, 2))
        self.assertEqual(len(self.overview(page=2).data['data']), 2)

from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from AuthManagement.models import User
from FeedbackManagement.models import Feedback, FeedbackComment


class FeedbackAPITests(APITestCase):
    def setUp(self):
        self.member = self.user('member', '01710000001')
        self.other_member = self.user('other', '01710000002')
        self.client.force_authenticate(user=self.member)

    def user(self, name, phone):
        return User.objects.create_user(email=f'{name}@test.com', phone=phone, full_name=name.title(), password='pass12345')

    def feedback(self, **kwargs):
        return Feedback.objects.create(user=kwargs.pop('user', self.member), description=kwargs.pop('description', 'Feedback'), **kwargs)

    def test_feedback_is_public_by_default_and_only_admin_controls_visibility(self):
        response = self.client.post('/api/v1/user/feedbacks', {'description': ' Public feedback ', 'is_public': 'false'}, format='multipart')

        self.assertEqual(response.status_code, 201, response.data)
        public_feedback = Feedback.objects.get()
        self.assertTrue(public_feedback.is_public)
        self.assertEqual(public_feedback.description, 'Public feedback')
        self.feedback(user=self.other_member, description='Private feedback', is_public=False)

        response = self.client.get('/api/v1/user/feedbacks')

        self.assertEqual([item['description'] for item in response.data['data']], ['Public feedback'])

    def test_public_feedback_is_shared_across_users(self):
        self.feedback(user=self.other_member, description='Other user feedback')
        self.feedback(description='My feedback')

        response = self.client.get('/api/v1/user/feedbacks')

        self.assertEqual([item['description'] for item in response.data['data']], ['My feedback', 'Other user feedback'])

    def test_submission_rejects_more_than_three_images_without_creating_feedback(self):
        images = [SimpleUploadedFile(f'image-{index}.png', b'image', content_type='image/png') for index in range(4)]

        response = self.client.post('/api/v1/user/feedbacks', {'description': 'Too many images', 'images': images}, format='multipart')

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_submission_rejects_a_file_that_only_claims_to_be_an_image(self):
        image = SimpleUploadedFile('image.png', b'not an image', content_type='image/png')

        response = self.client.post('/api/v1/user/feedbacks', {'description': 'Invalid image', 'images': [image]}, format='multipart')

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_invalid_page_returns_validation_error(self):
        response = self.client.get('/api/v1/user/feedbacks', {'page': 'invalid'})

        self.assertEqual(response.status_code, 400, response.data)

    def test_author_email_is_not_used_as_public_name(self):
        self.member.full_name = ''
        self.member.save(update_fields=['full_name'])
        self.feedback(description='No name')

        response = self.client.get('/api/v1/user/feedbacks')

        self.assertEqual(response.data['data'][0]['author_name'], 'Member')
        self.assertNotIn(self.member.email, str(response.data))

    def test_comments_flow_and_comments_count(self):
        feedback = self.feedback(description='System idea')

        response = self.client.post(f'/api/v1/user/feedbacks/{feedback.id}/comments', {'comment': 'Great system idea!'}, format='multipart')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['comment'], 'Great system idea!')
        self.assertTrue(response.data['is_author'])
        comments = self.client.get(f'/api/v1/user/feedbacks/{feedback.id}/comments')
        self.assertEqual((comments.status_code, comments.data['comments_count']), (200, 1))
        self.assertEqual(self.client.get('/api/v1/user/feedbacks').data['data'][0]['comments_count'], 1)

    def test_comments_are_paginated_twenty_at_a_time(self):
        feedback = self.feedback()
        FeedbackComment.objects.bulk_create([FeedbackComment(feedback=feedback, user=self.other_member, comment=f'Comment {index}') for index in range(21)])

        first = self.client.get(f'/api/v1/user/feedbacks/{feedback.id}/comments')
        second = self.client.get(f'/api/v1/user/feedbacks/{feedback.id}/comments', {'page': 2})

        self.assertEqual((len(first.data['data']), first.data['comments_count'], first.data['next_page']), (20, 21, 2))
        self.assertEqual((len(second.data['data']), second.data['comments_count'], second.data['next_page']), (1, 21, None))

    def test_private_feedback_comments_are_not_exposed(self):
        private = self.feedback(is_public=False)
        FeedbackComment.objects.create(feedback=private, user=self.other_member, comment='Private comment')

        self.assertEqual(self.client.get(f'/api/v1/user/feedbacks/{private.id}/comments').status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/user/feedbacks/{private.id}/comments', {'comment': 'Unauthorized'}, format='multipart').status_code, 404)

    def test_comment_rejects_a_file_that_only_claims_to_be_an_image(self):
        feedback = self.feedback()
        image = SimpleUploadedFile('image.png', b'not an image', content_type='image/png')

        response = self.client.post(f'/api/v1/user/feedbacks/{feedback.id}/comments', {'comment': 'Invalid image', 'image': image}, format='multipart')

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(FeedbackComment.objects.count(), 0)

    def test_django_admin_can_change_public_visibility(self):
        feedback_admin = admin.site._registry[Feedback]

        self.assertIn('is_public', feedback_admin.list_display)
        self.assertIn('is_public', feedback_admin.list_editable)

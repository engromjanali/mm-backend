import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from .models import User

IN_MEMORY_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


def png(name='photo.png', size=(4, 4)):
    buf = io.BytesIO()
    Image.new('RGB', size, (31, 164, 99)).save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(STORAGES=IN_MEMORY_STORAGES, FILE_UPLOAD_MAX_MEMORY_SIZE=10)
class ProfilePhotoTests(APITestCase):
    """FILE_UPLOAD_MAX_MEMORY_SIZE=10 forces temp-file uploads, like real photos."""

    def setUp(self):
        self.user = User.objects.create_user(email='me@test.com', phone='01700000000', full_name='Me', password='pass12345')
        self.client.force_authenticate(user=self.user)

    def test_multipart_update_saves_photo_with_other_fields(self):
        response = self.client.patch('/api/v1/auth/update-profile', {'full_name': 'New Name', 'photo': png()}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, 'New Name')
        self.assertTrue(self.user.photo.name.startswith('profile_photos/'))
        self.assertTrue(response.data['user']['photo'])

    def test_replacing_photo_deletes_old_file(self):
        self.client.patch('/api/v1/auth/update-profile', {'photo': png('a.png')}, format='multipart')
        self.user.refresh_from_db()
        old_name = self.user.photo.name
        self.client.patch('/api/v1/auth/update-profile', {'photo': png('b.png')}, format='multipart')
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.photo.name, old_name)
        self.assertFalse(self.user.photo.storage.exists(old_name))

"""
Cloudinary-backed media storage.

Every uploaded file (e.g. ``User.photo``) is stored in Cloudinary under the
``mm/`` folder, keeping the field's ``upload_to`` path as a sub-folder:
``profile_photos/me.jpg`` -> ``mm/profile_photos/<unique id>.jpg``.

The stored name is the Cloudinary public id plus extension, so ``.url``
rebuilds the secure delivery URL without an API call.
"""
import posixpath

import cloudinary.uploader
import cloudinary.utils
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

CLOUDINARY_ROOT_FOLDER = 'mm'


@deconstructible
class CloudinaryMediaStorage(Storage):
    def _split(self, name):
        public_id, ext = posixpath.splitext(name)
        return public_id, ext.lstrip('.')

    def _save(self, name, content):
        folder = posixpath.join(CLOUDINARY_ROOT_FOLDER, posixpath.dirname(name)).rstrip('/')
        content.seek(0)
        result = cloudinary.uploader.upload(
            content,
            folder=folder,
            resource_type='auto',
            unique_filename=True,
            use_filename=False,
            overwrite=False,
        )
        ext = result.get('format') or self._split(name)[1]
        return f"{result['public_id']}.{ext}" if ext else result['public_id']

    def url(self, name):
        if not name:
            return ''
        public_id, ext = self._split(name)
        return cloudinary.utils.cloudinary_url(public_id, format=ext or None, secure=True)[0]

    def delete(self, name):
        if name:
            cloudinary.uploader.destroy(self._split(name)[0], invalidate=True)

    def exists(self, name):
        # Cloudinary generates a unique public id on upload, so names never collide.
        return False

    def get_available_name(self, name, max_length=None):
        return name

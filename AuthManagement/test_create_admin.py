from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import User


class CreateAdminCommandTests(TestCase):
    def run_command(self, **options):
        out = StringIO()
        call_command("create_admin", interactive=False, stdout=out, **options)
        return out.getvalue()

    def test_creates_superuser(self):
        output = self.run_command(email="Admin@Example.com", phone="01700000000", full_name="Admin", password="secret123")

        user = User.objects.get(email="admin@example.com")
        self.assertTrue(user.is_superuser and user.is_staff and user.is_active)
        self.assertTrue(user.check_password("secret123"))
        self.assertIn("created", output)

    def test_promotes_existing_user_and_keeps_password_when_none_given(self):
        user = User.objects.create_user("member@example.com", "01700000001", "Member", "oldpass1")

        output = self.run_command(email="member@example.com")

        user.refresh_from_db()
        self.assertTrue(user.is_superuser and user.is_staff)
        self.assertTrue(user.check_password("oldpass1"))
        self.assertIn("password unchanged", output)

    def test_promoting_existing_user_updates_password_when_given(self):
        user = User.objects.create_user("member@example.com", "01700000001", "Member", "oldpass1")

        self.run_command(email="member@example.com", password="newpass1")

        user.refresh_from_db()
        self.assertTrue(user.check_password("newpass1"))

    def test_rejects_phone_used_by_another_user(self):
        User.objects.create_user("member@example.com", "01700000001", "Member", "oldpass1")

        with self.assertRaisesMessage(CommandError, "The phone 01700000001 already belongs to member@example.com."):
            self.run_command(email="admin@example.com", phone="01700000001", full_name="Admin", password="secret123")

    def test_requires_password_without_input(self):
        with self.assertRaisesMessage(CommandError, "A password is required"):
            self.run_command(email="admin@example.com", phone="01700000000", full_name="Admin")
        self.assertFalse(User.objects.filter(email="admin@example.com").exists())

    def test_rejects_short_password(self):
        with self.assertRaisesMessage(CommandError, "Password rejected"):
            self.run_command(email="admin@example.com", phone="01700000000", full_name="Admin", password="123")

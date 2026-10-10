import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from AuthManagement.models import User


class Command(BaseCommand):
    help = (
        "Creates a Django admin (superuser), or makes an existing user one. Values come from the flags, "
        "else DJANGO_ADMIN_EMAIL / DJANGO_ADMIN_PHONE / DJANGO_ADMIN_FULL_NAME / DJANGO_ADMIN_PASSWORD; "
        "a missing password is asked for unless --no-input is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", default=os.environ.get("DJANGO_ADMIN_EMAIL"))
        parser.add_argument("--phone", default=os.environ.get("DJANGO_ADMIN_PHONE"))
        parser.add_argument("--full-name", default=os.environ.get("DJANGO_ADMIN_FULL_NAME"))
        parser.add_argument("--password", default=os.environ.get("DJANGO_ADMIN_PASSWORD"))
        parser.add_argument("--no-input", action="store_false", dest="interactive", help="Never prompt; fail when the password is missing.")

    def handle(self, *args, email, phone, full_name, password, interactive, **options):
        email = User.objects.normalize_email((email or "").strip()).lower()
        if not email:
            raise CommandError("An email address is required (--email or DJANGO_ADMIN_EMAIL).")

        user = User.objects.filter(email=email).first()
        if user:
            self._promote(user, password)
            return

        phone = (phone or "").strip()
        full_name = (full_name or "").strip()
        if not phone:
            raise CommandError("A phone number is required for a new admin (--phone or DJANGO_ADMIN_PHONE).")
        if not full_name:
            raise CommandError("A full name is required for a new admin (--full-name or DJANGO_ADMIN_FULL_NAME).")
        taken_by = User.objects.filter(phone=phone).values_list("email", flat=True).first()
        if taken_by:
            raise CommandError(f"The phone {phone} already belongs to {taken_by}.")

        user = User(email=email, phone=phone, full_name=full_name)
        password = password or self._ask_password(interactive)
        self._check_password(password, user)
        User.objects.create_superuser(email, phone, full_name, password)
        self.stdout.write(self.style.SUCCESS(f"Admin {email} created."))

    def _promote(self, user, password):
        """Makes an existing user an active superuser; sets the password only when one is given."""
        user.is_staff = user.is_superuser = user.is_active = True
        if password:
            self._check_password(password, user)
            user.set_password(password)
        user.save()
        password_note = "password updated" if password else "password unchanged"
        self.stdout.write(self.style.SUCCESS(f"{user.email} already existed; it is now an admin ({password_note})."))

    def _ask_password(self, interactive):
        if not interactive:
            raise CommandError("A password is required for a new admin (--password or DJANGO_ADMIN_PASSWORD).")
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("The two passwords don't match.")
        return password

    def _check_password(self, password, user):
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(f"Password rejected: {' '.join(error.messages)}")

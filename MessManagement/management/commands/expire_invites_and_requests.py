from django.core.management.base import BaseCommand

from MessManagement.utils import expire_stale_invites_and_requests


class Command(BaseCommand):
    help = "Marks invitations and join requests still pending 7 days after they were sent as expired. Run nightly."

    def handle(self, *args, **options):
        invites, requests = expire_stale_invites_and_requests()
        self.stdout.write(self.style.SUCCESS(f"{invites} invitation(s) and {requests} join request(s) expired."))

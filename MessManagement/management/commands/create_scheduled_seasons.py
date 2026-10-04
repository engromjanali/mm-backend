from django.core.management.base import BaseCommand
from django.utils import timezone

from MessManagement.utils import run_auto_create_seasons


class Command(BaseCommand):
    help = "Creates today's auto-created seasons (messes with auto-create on whose day is today). Run once a day."

    def handle(self, *args, **options):
        created = run_auto_create_seasons(timezone.localdate())
        for season in created:
            self.stdout.write(f"{season.mess.name}: created {season.name}")
        self.stdout.write(self.style.SUCCESS(f"{len(created)} season(s) created."))

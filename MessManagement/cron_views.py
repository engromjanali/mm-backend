"""
Scheduled jobs, called by Vercel Cron (see ``vercel.json``) under ``/api/v1/cron/``.

Not user or admin endpoints: no JWT, but every call must carry
``Authorization: Bearer <CRON_SECRET>``, which Vercel adds when the
``CRON_SECRET`` environment variable is set.
"""
import hmac

from django.conf import settings
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .utils import expire_stale_invites_and_requests, mess_today, run_auto_create_seasons


class CronView(APIView):
    """Base for cron endpoints: rejects calls without the cron secret."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        secret = settings.CRON_SECRET
        if not secret:
            raise PermissionDenied("Cron jobs are disabled: CRON_SECRET isn't configured.")
        if not hmac.compare_digest(request.headers.get('Authorization', ''), f'Bearer {secret}'):
            raise PermissionDenied("Invalid cron secret.")


class ExpireInvitesAndRequestsCronView(CronView):
    """
    GET /api/v1/cron/expire-invites-and-requests  — nightly, 11:30 PM Bangladesh time

    Saves ``expired`` on invitations and join requests still pending 7 days
    after they were sent.
    """

    def get(self, request):
        invites, requests = expire_stale_invites_and_requests()
        return Response({"message": f"{invites} invitation(s) and {requests} join request(s) expired.", "invites": invites, "requests": requests})


class CreateScheduledSeasonsCronView(CronView):
    """
    GET /api/v1/cron/create-scheduled-seasons  — nightly, 12:05 AM Bangladesh time

    For every mess whose auto-create day is today (in ``MESS_TIME_ZONE``),
    creates a ``season-xyz`` from its active season and switches the members
    working in it. Runs at most once per mess per day, so a repeated call is safe.
    """

    def get(self, request):
        created = run_auto_create_seasons(mess_today())
        return Response({
            "message": f"{len(created)} season(s) created.",
            "seasons": [{"mess_id": season.mess_id, "mess_name": season.mess.name, "season_id": season.id, "season_name": season.name} for season in created],
        })

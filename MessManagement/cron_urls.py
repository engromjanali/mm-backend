from django.urls import path

from .cron_views import CreateScheduledSeasonsCronView, ExpireInvitesAndRequestsCronView

urlpatterns = [
    path('expire-invites-and-requests', ExpireInvitesAndRequestsCronView.as_view(), name='cron-expire-invites-and-requests'),
    path('create-scheduled-seasons', CreateScheduledSeasonsCronView.as_view(), name='cron-create-scheduled-seasons'),
]

from django.urls import path

from .membership_views import (
    AdminInviteView,
    AdminJoinRequestDecisionView,
    AdminJoinRequestListView,
    AdminMemberListView,
    AdminSeasonView,
    MemberLookupView,
)

urlpatterns = [
    path('member-lookup', MemberLookupView.as_view(), name='admin-member-lookup'),
    path('invites', AdminInviteView.as_view(), name='admin-invites'),
    path('join-requests', AdminJoinRequestListView.as_view(), name='admin-join-requests'),
    path('join-requests/decision', AdminJoinRequestDecisionView.as_view(), name='admin-join-request-decision'),
    path('members', AdminMemberListView.as_view(), name='admin-members'),
    path('seasons', AdminSeasonView.as_view(), name='admin-seasons'),
]

from django.urls import path

from .membership_views import (
    AdminActingManagerView,
    AdminInviteView,
    AdminJoinRequestDecisionView,
    AdminJoinRequestListView,
    AdminMemberListView,
    AdminMemberStatusView,
    AdminTransferOwnershipView,
    MemberLookupView,
)
from .notice_views import AdminNoticeCreateView, AdminNoticeDetailView, AdminNoticePinView
from .season_views import (
    AdminSeasonAutoCreateView,
    AdminSeasonDetailView,
    AdminSeasonEndView,
    AdminSeasonListView,
    AdminSeasonStatusView,
    AdminSeasonSwitchView,
)

urlpatterns = [
    path('member-lookup', MemberLookupView.as_view(), name='admin-member-lookup'),
    path('invites', AdminInviteView.as_view(), name='admin-invites'),
    path('join-requests', AdminJoinRequestListView.as_view(), name='admin-join-requests'),
    path('join-requests/decision', AdminJoinRequestDecisionView.as_view(), name='admin-join-request-decision'),
    path('members', AdminMemberListView.as_view(), name='admin-members'),
    path('members/<int:pk>/disable', AdminMemberStatusView.as_view(disable=True), name='admin-member-disable'),
    path('members/<int:pk>/enable', AdminMemberStatusView.as_view(disable=False), name='admin-member-enable'),
    path('members/<int:pk>/acting-manager', AdminActingManagerView.as_view(), name='admin-member-acting-manager'),
    path('members/<int:pk>/transfer-ownership', AdminTransferOwnershipView.as_view(), name='admin-member-transfer-ownership'),
    path('seasons', AdminSeasonListView.as_view(), name='admin-seasons'),
    path('seasons/auto-create', AdminSeasonAutoCreateView.as_view(), name='admin-season-auto-create'),
    path('seasons/<int:pk>', AdminSeasonDetailView.as_view(), name='admin-season-detail'),
    path('seasons/<int:pk>/end', AdminSeasonEndView.as_view(), name='admin-season-end'),
    path('seasons/<int:pk>/disable', AdminSeasonStatusView.as_view(disable=True), name='admin-season-disable'),
    path('seasons/<int:pk>/enable', AdminSeasonStatusView.as_view(disable=False), name='admin-season-enable'),
    path('seasons/<int:pk>/switch', AdminSeasonSwitchView.as_view(), name='admin-season-switch'),
    path('notices', AdminNoticeCreateView.as_view(), name='admin-notices'),
    path('notices/<int:pk>', AdminNoticeDetailView.as_view(), name='admin-notice-detail'),
    path('notices/<int:pk>/pin', AdminNoticePinView.as_view(), name='admin-notice-pin'),
]

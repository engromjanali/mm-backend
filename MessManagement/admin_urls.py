from django.urls import path

from .membership_views import (
    AdminActingManagerView,
    AdminInviteView,
    AdminJoinRequestDecisionView,
    AdminJoinRequestListView,
    AdminMemberListView,
    AdminMemberStatusView,
    AdminSeasonView,
    AdminTransferOwnershipView,
    MemberLookupView,
)
from .notice_views import AdminNoticeCreateView, AdminNoticeDetailView, AdminNoticePinView

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
    path('seasons', AdminSeasonView.as_view(), name='admin-seasons'),
    path('notices', AdminNoticeCreateView.as_view(), name='admin-notices'),
    path('notices/<int:pk>', AdminNoticeDetailView.as_view(), name='admin-notice-detail'),
    path('notices/<int:pk>/pin', AdminNoticePinView.as_view(), name='admin-notice-pin'),
]

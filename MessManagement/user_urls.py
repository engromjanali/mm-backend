from django.urls import path

from .membership_views import (
    CreateMessView,
    InviteResponseView,
    JoinRequestView,
    LeaveMessView,
    MembershipStatusView,
    PublicMessListView,
    SwitchMembershipView,
)
from .mess_views import MyMessView
from .notice_views import NoticeListView

urlpatterns = [
    path('messes', PublicMessListView.as_view(), name='user-messes'),
    path('messes/create', CreateMessView.as_view(), name='user-mess-create'),
    path('membership/status', MembershipStatusView.as_view(), name='user-membership-status'),
    path('membership/leave', LeaveMessView.as_view(), name='user-membership-leave'),
    path('membership/switch', SwitchMembershipView.as_view(), name='user-membership-switch'),
    path('mess', MyMessView.as_view(), name='user-mess'),
    path('join-requests', JoinRequestView.as_view(), name='user-join-requests'),
    path('join-requests/<int:pk>', JoinRequestView.as_view(), name='user-join-request-cancel'),
    path('invites/accept', InviteResponseView.as_view(accept=True), name='user-invite-accept'),
    path('invites/decline', InviteResponseView.as_view(accept=False), name='user-invite-decline'),
    path('notices', NoticeListView.as_view(), name='user-notices'),
]

from django.urls import path

from .notifications import NotificationListView, NotificationOpenView
from .views import AccountDeletionView

urlpatterns = [
    path('notifications', NotificationListView.as_view(), name='user-notifications'),
    path('notifications/<int:pk>/open', NotificationOpenView.as_view(), name='user-notification-open'),
    path('account/delete', AccountDeletionView.as_view(), name='user-account-delete'),
]

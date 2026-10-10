from django.urls import path

from .views import AccountDeletionView

urlpatterns = [
    path('account/delete', AccountDeletionView.as_view(), name='user-account-delete'),
]

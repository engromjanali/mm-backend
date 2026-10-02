from django.urls import path

from .views import MyDepositListView

urlpatterns = [
    path('deposits', MyDepositListView.as_view(), name='user-deposits'),
]

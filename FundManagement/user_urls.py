from django.urls import path

from .views import FundListView

urlpatterns = [
    path('funds', FundListView.as_view(), name='user-funds'),
]

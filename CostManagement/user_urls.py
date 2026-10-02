from django.urls import path

from .views import CostListView

urlpatterns = [
    path('costs', CostListView.as_view(), name='user-costs'),
]

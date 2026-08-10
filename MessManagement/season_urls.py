from django.urls import path

from .views import StartNewSeasonView

app_name = "season_management"

urlpatterns = [
    path('start-new-season', StartNewSeasonView.as_view(), name='start-new-season'),
]

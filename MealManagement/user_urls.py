from django.urls import path

from .views import MyMealListView

urlpatterns = [
    path('meals', MyMealListView.as_view(), name='user-meals'),
]

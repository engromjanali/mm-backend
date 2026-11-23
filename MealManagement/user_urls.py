from django.urls import path

from .views import MealRequestListView, MealRequestSelectionView, MyMealListView

urlpatterns = [
    path('meals', MyMealListView.as_view(), name='user-meals'),
    path('meal-requests', MealRequestListView.as_view(), name='user-meal-requests'),
    path('meal-requests/<int:pk>', MealRequestSelectionView.as_view(), name='user-meal-request-selection'),
]

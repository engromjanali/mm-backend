from django.urls import path

from .views import (
    MealAddView,
    MealDeleteView,
    MealDetailView,
    MealListAllView,
    MealListView,
    MealUpdateView,
)

app_name = "meal"

urlpatterns = [
    path('add/', MealAddView.as_view(), name='meal-add'),
    path('add', MealAddView.as_view(), name='meal-add-no-slash'),
    path('update/', MealUpdateView.as_view(), name='meal-update'),
    path('update', MealUpdateView.as_view(), name='meal-update-no-slash'),
    path('update/<int:pk>/', MealUpdateView.as_view(), name='meal-update-pk'),
    path('update/<int:pk>', MealUpdateView.as_view(), name='meal-update-pk-no-slash'),
    path('delete/', MealDeleteView.as_view(), name='meal-delete'),
    path('delete', MealDeleteView.as_view(), name='meal-delete-no-slash'),
    path('delete/<int:pk>/', MealDeleteView.as_view(), name='meal-delete-pk'),
    path('delete/<int:pk>', MealDeleteView.as_view(), name='meal-delete-pk-no-slash'),
    path('list/', MealListView.as_view(), name='meal-list'),
    path('list', MealListView.as_view(), name='meal-list-no-slash'),
    path('list-all/', MealListAllView.as_view(), name='meal-list-all'),
    path('list-all', MealListAllView.as_view(), name='meal-list-all-no-slash'),
    path('<int:pk>/', MealDetailView.as_view(), name='meal-detail'),
    path('<int:pk>', MealDetailView.as_view(), name='meal-detail-no-slash'),
]

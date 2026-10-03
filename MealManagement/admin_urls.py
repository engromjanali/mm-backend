from django.urls import path

from .views import AdminMealBulkView, AdminMealView

urlpatterns = [
    path('meals', AdminMealView.as_view(), name='admin-meals'),
    path('meals/bulk', AdminMealBulkView.as_view(), name='admin-meals-bulk'),
]

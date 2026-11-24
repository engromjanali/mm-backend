from django.urls import path

from .views import AdminMealBulkView, AdminMealRequestCloseView, AdminMealRequestReopenView, AdminMealRequestsApplyView, AdminMealRequestsView, AdminMealView

urlpatterns = [
    path('meals', AdminMealView.as_view(), name='admin-meals'),
    path('meals/bulk', AdminMealBulkView.as_view(), name='admin-meals-bulk'),
    path('meal-requests', AdminMealRequestsView.as_view(), name='admin-meal-requests'),
    path('meal-requests/apply', AdminMealRequestsApplyView.as_view(), name='admin-meal-requests-apply'),
    path('meal-requests/<int:pk>', AdminMealRequestsView.as_view(), name='admin-meal-request-detail'),
    path('meal-requests/<int:pk>/close', AdminMealRequestCloseView.as_view(), name='admin-meal-request-close'),
    path('meal-requests/<int:pk>/reopen', AdminMealRequestReopenView.as_view(), name='admin-meal-request-reopen'),
]

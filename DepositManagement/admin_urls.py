from django.urls import path

from .views import AdminDepositDetailView, AdminDepositListCreateView, AdminDepositSummaryView

urlpatterns = [
    path('deposits', AdminDepositListCreateView.as_view(), name='admin-deposits'),
    path('deposits/summary', AdminDepositSummaryView.as_view(), name='admin-deposit-summary'),
    path('deposits/<int:pk>', AdminDepositDetailView.as_view(), name='admin-deposit-detail'),
]

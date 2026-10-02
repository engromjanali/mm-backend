from django.urls import path

from .views import AdminFundCreateView, AdminFundDetailView

urlpatterns = [
    path('funds', AdminFundCreateView.as_view(), name='admin-funds'),
    path('funds/<int:pk>', AdminFundDetailView.as_view(), name='admin-fund-detail'),
]

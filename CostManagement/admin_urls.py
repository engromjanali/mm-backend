from django.urls import path

from .views import AdminCostCreateView, AdminCostDetailView

urlpatterns = [
    path('costs', AdminCostCreateView.as_view(), name='admin-costs'),
    path('costs/<int:pk>', AdminCostDetailView.as_view(), name='admin-cost-detail'),
]

from django.urls import path

from .views import AdminPollCloseView, AdminPollDetailView, AdminPollListCreateView, AdminPollResultsView

urlpatterns = [
    path('polls', AdminPollListCreateView.as_view(), name='admin-polls'),
    path('polls/<int:pk>', AdminPollDetailView.as_view(), name='admin-poll-detail'),
    path('polls/<int:pk>/close', AdminPollCloseView.as_view(), name='admin-poll-close'),
    path('polls/<int:pk>/results', AdminPollResultsView.as_view(), name='admin-poll-results'),
]

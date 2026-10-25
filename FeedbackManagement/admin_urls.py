from django.urls import path

from .views import AdminFeedbackListView, AdminFeedbackDeleteView

urlpatterns = [
    path('feedbacks', AdminFeedbackListView.as_view(), name='admin-feedbacks'),
    path('feedbacks/<int:pk>', AdminFeedbackDeleteView.as_view(), name='admin-feedback-delete'),
]

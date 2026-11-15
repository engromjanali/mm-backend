from django.urls import path

from .views import FeedbackListView, FeedbackCommentListView

urlpatterns = [
    path('feedbacks', FeedbackListView.as_view(), name='user-feedbacks'),
    path('feedbacks/<int:feedback_id>/comments', FeedbackCommentListView.as_view(), name='user-feedback-comments'),
]

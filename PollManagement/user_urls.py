from django.urls import path

from .views import PollDetailView, PollListView, PollVoteView

urlpatterns = [
    path('polls', PollListView.as_view(), name='user-polls'),
    path('polls/<int:pk>', PollDetailView.as_view(), name='user-poll-detail'),
    path('polls/<int:pk>/vote', PollVoteView.as_view(), name='user-poll-vote'),
]

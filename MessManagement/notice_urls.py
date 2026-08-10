from django.urls import path
from .views import (
    NoticeCreateView,
    NoticeUpdateView,
    NoticeDeleteView,
    NoticeListView,
    NoticeDetailView,
    NoticePinnedView,
    NoticeSetPinnedView,
)

app_name = "notice"

urlpatterns = [
    path('create/', NoticeCreateView.as_view(), name='notice-create'),
    path('create', NoticeCreateView.as_view(), name='notice-create-no-slash'),
    path('update/', NoticeUpdateView.as_view(), name='notice-update'),
    path('update', NoticeUpdateView.as_view(), name='notice-update-no-slash'),
    path('update/<int:pk>/', NoticeUpdateView.as_view(), name='notice-update-pk'),
    path('update/<int:pk>', NoticeUpdateView.as_view(), name='notice-update-pk-no-slash'),
    path('delete/', NoticeDeleteView.as_view(), name='notice-delete'),
    path('delete', NoticeDeleteView.as_view(), name='notice-delete-no-slash'),
    path('delete/<int:pk>/', NoticeDeleteView.as_view(), name='notice-delete-pk'),
    path('delete/<int:pk>', NoticeDeleteView.as_view(), name='notice-delete-pk-no-slash'),
    path('list/', NoticeListView.as_view(), name='notice-list'),
    path('list', NoticeListView.as_view(), name='notice-list-no-slash'),
    path('pin/', NoticePinnedView.as_view(), name='notice-pin'),
    path('pin', NoticePinnedView.as_view(), name='notice-pin-no-slash'),
    path('set-pined-notice/', NoticeSetPinnedView.as_view(), name='notice-set-pinned'),
    path('set-pined-notice', NoticeSetPinnedView.as_view(), name='notice-set-pinned-no-slash'),
    path('<int:pk>/', NoticeDetailView.as_view(), name='notice-detail'),
    path('<int:pk>', NoticeDetailView.as_view(), name='notice-detail-no-slash'),
]

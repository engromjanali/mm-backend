from django.urls import path

from .views import AppConfigView, ContentPageView, FaqListView

urlpatterns = [
    path('config', AppConfigView.as_view(), name='app-config'),
    path('pages/<slug:kind>', ContentPageView.as_view(), name='app-content-page'),
    path('faqs', FaqListView.as_view(), name='app-faqs'),
]

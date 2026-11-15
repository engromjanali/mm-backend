from django.urls import path

from .views import AppConfigView, ContentPageView, FaqListView

urlpatterns = [
    path('config', AppConfigView.as_view(), name='app-config'),
    path('pages/<slug:kind>', ContentPageView.as_view(), name='app-content-page'),
    path('privacy-policy', ContentPageView.as_view(), {'kind': 'privacy-policy'}, name='app-privacy-policy'),
    path('terms-and-conditions', ContentPageView.as_view(), {'kind': 'terms-and-conditions'}, name='app-terms-and-conditions'),
    path('faqs', FaqListView.as_view(), name='app-faqs'),
]

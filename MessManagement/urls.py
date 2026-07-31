from django.urls import path

from .views import MessCreationView, MessListView, MessManagementTest

app_name = "mess_management"

urlpatterns = [
    path('test/', MessManagementTest, name='mess-management-test'),
    path('create/', MessCreationView.as_view(), name='mess-create'),
    path('create', MessCreationView.as_view(), name='mess-create-no-slash'),
    path('list/', MessListView.as_view(), name='mess-list'),
    path('list', MessListView.as_view(), name='mess-list-no-slash'),
]
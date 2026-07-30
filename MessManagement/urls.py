from django.urls import path

from .views import MessCreationView, MessManagementTest

app_name = "mess_management"

urlpatterns = [
    path('test/', MessManagementTest, name='mess-management-test'),
    path('create/', MessCreationView.as_view(), name='mess-create'),
    path('create', MessCreationView.as_view(), name='mess-create-no-slash'),
]
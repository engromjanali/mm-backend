from django.urls import path
from .views import MessManagementTest

urlpatterns = [
    path('test/', MessManagementTest, name='mess-management-test')
]
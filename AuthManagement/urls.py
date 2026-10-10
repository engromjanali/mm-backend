from django.urls import path

from .views import (
    ChangePasswordView,
    ForgotPasswordView,
    ProfileView,
    RefreshTokenView,
    SignInView,
    SignUpView,
    UpdateProfileView,
    testfunc,
)
from ContentManagement.views import AppConfigView

app_name = "auth_management"

urlpatterns = [
    # Older app builds read the config here; it now lives at /api/v1/app/config.
    path('config', AppConfigView.as_view(), name='config'),
    path("test", testfunc, name="test"),
    path("sign-in", SignInView.as_view(), name="sign-in"),
    path("sign-up", SignUpView.as_view(), name="sign-up"),
    path("refresh-token", RefreshTokenView.as_view(), name="refresh-token"),
    path("forgot-password", ForgotPasswordView.as_view(), name="forgot-password"),
    path("change-password", ChangePasswordView.as_view(), name="change-password"),
    path("profile", ProfileView.as_view(), name="profile"),
    path("update-profile", UpdateProfileView.as_view(), name="update-profile"),
]

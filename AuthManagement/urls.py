from django.urls import path

from .views import (
    ChangePasswordView,
    ForgotPasswordView,
    ProfileView,
    SignInView,
    SignUpView,
    UpdateProfileView,
    testfunc,
    config
)

app_name = "auth_management"

urlpatterns = [
    path('config', config, name='config'),
    path("test", testfunc, name="test"),
    path("sign-in", SignInView.as_view(), name="sign-in"),
    path("sign-up", SignUpView.as_view(), name="sign-up"),
    path("forgot-password", ForgotPasswordView.as_view(), name="forgot-password"),
    path("forget-password", ForgotPasswordView.as_view(), name="forget-password"),
    path("change-password", ChangePasswordView.as_view(), name="change-password"),
    path("profile", ProfileView.as_view(), name="profile"),
    path("update-profile", UpdateProfileView.as_view(), name="update-profile"),
]

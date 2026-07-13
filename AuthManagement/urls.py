from django.urls import path

from .views import (
    ChangePasswordView,
    ForgotPasswordView,
    SignInView,
    SignUpView,
    UpdateProfileView,
    testfunc,
)

app_name = "auth_management"

urlpatterns = [
    path("test", testfunc, name="test"),
    path("sign-in", SignInView.as_view(), name="sign-in"),
    path("sign-up", SignUpView.as_view(), name="sign-up"),
    path("forgot-password", ForgotPasswordView.as_view(), name="forgot-password"),
    path("forget-password", ForgotPasswordView.as_view(), name="forget-password"),
    path("change-password", ChangePasswordView.as_view(), name="change-password"),
    path("update-profile", UpdateProfileView.as_view(), name="update-profile"),
]

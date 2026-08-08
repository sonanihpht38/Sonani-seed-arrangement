# Auth routes mounted under /api/auth/ by the project urls.
from django.urls import path

from .views import ForgotPasswordView, MeView, RegisterView, ResetPasswordView

urlpatterns = [
    path("me", MeView.as_view(), name="auth-me"),
    path("register", RegisterView.as_view(), name="auth-register"),  # public
    path("forgot-password", ForgotPasswordView.as_view(), name="auth-forgot-password"),  # public
    path("reset-password", ResetPasswordView.as_view(), name="auth-reset-password"),  # public
]

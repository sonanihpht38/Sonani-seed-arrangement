# ============================= API LAYER =============================
# Identity only: /me (who am I + my effective permissions) and the public
# self-service auth flows (register, forgot/reset password). User administration
# is done from the Django admin — a self-registered account stays inactive until
# a superuser sets is_active/is_verified there.

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .serializers import (
    ForgotPasswordSerializer, MeSerializer, RegisterSerializer, ResetPasswordSerializer,
)
from .services import PasswordResetService, RegistrationService


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class RegisterView(APIView):
    """Public self-registration. Creates an active account with production access
    (see RegistrationService), so the user can sign in immediately."""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        RegistrationService.register(s.validated_data)
        return Response(
            {"detail": "Account created. You can sign in now."},
            status=status.HTTP_201_CREATED,
        )


class ForgotPasswordView(APIView):
    """Public: email a password-reset link. Always 200 (never leaks whether the
    address is registered)."""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        s = ForgotPasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        PasswordResetService.request(s.validated_data["email"])
        return Response({"detail": "If that email is registered, a reset link has been sent."})


class ResetPasswordView(APIView):
    """Public: complete a password reset with the emailed uid + token."""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        s = ResetPasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        PasswordResetService.reset(
            s.validated_data["uid"], s.validated_data["token"], s.validated_data["new_password"])
        return Response({"detail": "Your password has been reset. You can now sign in."})

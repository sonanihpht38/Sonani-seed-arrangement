# ===================== APPLICATION LAYER: serializers (DTOs) =====================
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


# ---- Current user (/me) -----------------------------------------------------
class MeSerializer(serializers.ModelSerializer):
    """Current-user payload the frontend uses to drive nav + permission gating."""
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "full_name", "tenant_id",
                  "is_superuser", "roles", "permissions"]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_roles(self, obj):
        return [
            {"id": str(ur.role_id), "code": ur.role.code, "name": ur.role.name}
            for ur in obj.user_roles.select_related("role").all()
        ]

    def get_permissions(self, obj):
        # { form_code: {view, create, edit, delete} } — the effective union.
        from modules.access.services import PermissionService
        return PermissionService.effective_map(obj)


# ---- Public self-service auth flows -----------------------------------------
class ForgotPasswordSerializer(serializers.Serializer):
    """Public: request a password-reset email for an address."""
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    """Public: complete a reset with the emailed uid + token."""
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class RegisterSerializer(serializers.Serializer):
    """Public self-registration payload."""
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

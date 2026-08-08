# ===================== APPLICATION LAYER: services =====================
# Public self-service identity flows: registration and password reset. Creating,
# editing and role-assigning users is done from the Django admin. User-facing
# rule violations raise DRF ValidationError so views return 400 with a clean
# message automatically.

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

User = get_user_model()


# The role a self-registered user is granted so they can use the app right away.
# Provisioned by `manage.py ensure_production_role`.
DEFAULT_SIGNUP_ROLE = "PRODUCTION_USER"


class RegistrationService:
    """Public self-registration -> an ACTIVE user with production access.

    Policy: internal tool, self-service onboarding. A new account is enabled
    immediately and given the Production User role, so the person can sign in and
    work without an admin step. Tighten this (set is_active=False, drop the role
    grant) if signups should be gated instead.
    """

    @staticmethod
    @transaction.atomic
    def register(data):
        from modules.access.models import Role, UserRole
        from modules.masters.models import Company

        username = data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError({"username": "That username is already taken."})

        company = Company.objects.first()
        tenant_id = company.id if company else None
        user = User(
            username=username,
            email=data.get("email", ""),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            is_active=True,       # can sign in immediately
            is_verified=True,
            tenant_id=tenant_id,
        )
        user.set_password(data["password"])
        user.save()

        # Grant the default role so the app isn't empty on first login. If it
        # hasn't been provisioned yet (ensure_production_role), the account is
        # still created — an admin can assign a role later.
        if tenant_id is not None:
            role = Role.objects.filter(tenant_id=tenant_id, code=DEFAULT_SIGNUP_ROLE).first()
            if role is not None:
                UserRole.objects.get_or_create(user=user, role=role)
        return user


class PasswordResetService:
    """Email-based password reset using Django's signed token generator.

    ``request`` never reveals whether an address exists (anti-enumeration); it
    silently no-ops for unknown/inactive users. ``reset`` verifies the emailed
    uid+token and sets the new password.
    """

    @staticmethod
    def request(email):
        from django.conf import settings
        from django.contrib.auth.tokens import default_token_generator
        from django.core.mail import send_mail
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.filter(email__iexact=(email or "").strip(), is_active=True).first()
        if user is None or not user.email:
            return  # silent — don't leak which emails are registered
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
        name = user.get_full_name() or user.username
        send_mail(
            subject="Reset your Sonani Seed Arrangement password",
            message=(
                f"Hi {name},\n\n"
                "We received a request to reset your password. Use the link below "
                "to choose a new one (it expires shortly):\n\n"
                f"{link}\n\n"
                "If you didn't request this, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

    @staticmethod
    def reset(uid, token, new_password):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode

        try:
            pk = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=pk)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"detail": "Invalid or expired reset link."})
        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError({"detail": "Invalid or expired reset link."})
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return user

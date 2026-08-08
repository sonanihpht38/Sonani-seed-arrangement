# ===================== INFRASTRUCTURE LAYER: repository =====================
# Tenant-scoped access to roles/permissions. Forms and module groups are a global
# catalogue, so they aren't tenant-filtered; roles and grants always are.

from .models import (
    Form, GridColumn, ModuleGroup, Role, RoleColumnPermission, RoleFormPermission,
    UserColumnPermission, UserFormPermission, UserRole,
)


class CatalogueRepository:
    @staticmethod
    def groups():
        return ModuleGroup.objects.prefetch_related("forms").all()

    @staticmethod
    def forms():
        return Form.objects.filter(is_active=True)

    @staticmethod
    def form_by_code(code):
        return Form.objects.filter(code=code, is_active=True).first()


class RoleRepository:
    @staticmethod
    def for_tenant(tenant_id):
        return Role.objects.filter(tenant_id=tenant_id).order_by("code")

    @staticmethod
    def get(tenant_id, role_id):
        return Role.objects.filter(tenant_id=tenant_id, id=role_id).first()

    @staticmethod
    def permissions(role):
        return RoleFormPermission.objects.filter(role=role).select_related("form")


class UserAccessRepository:
    @staticmethod
    def role_ids_for_user(user):
        return list(UserRole.objects.filter(user=user).values_list("role_id", flat=True))

    @staticmethod
    def permissions_for_roles(role_ids):
        return (RoleFormPermission.objects
                .filter(role_id__in=role_ids)
                .select_related("form"))

    @staticmethod
    def user_permissions(user):
        return UserFormPermission.objects.filter(user=user).select_related("form")


class GridColumnRepository:
    """Column-level RBAC master + grants — one level deeper than Form access."""

    @staticmethod
    def for_form(form_code):
        return GridColumn.objects.filter(form__code=form_code, is_active=True).select_related("form")

    @staticmethod
    def get(column_id):
        return GridColumn.objects.filter(id=column_id).select_related("form").first()

    @staticmethod
    def role_permissions(role):
        return RoleColumnPermission.objects.filter(role=role).select_related("column", "column__form")

    @staticmethod
    def user_permissions(user):
        return UserColumnPermission.objects.filter(user=user).select_related("column", "column__form")

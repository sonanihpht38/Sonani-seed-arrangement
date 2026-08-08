# ===================== APPLICATION LAYER: services =====================
# Orchestration for roles + form permissions, and the single source of truth for
# "what can this user do" (PermissionService) — reused by the DRF permission class
# and by the /me endpoint.

from django.db import transaction

from .models import (
    DomainError, Role, RoleColumnPermission, RoleFormPermission,
    UserColumnPermission, UserRole,
)
from .repository import (
    CatalogueRepository, GridColumnRepository, RoleRepository, UserAccessRepository,
)

# Canonical stored actions. `save`/`update` are exposed as aliases of
# `create`/`edit` so both the legacy (view/create/edit/delete) and the new
# (view/save/update/delete/export) vocabularies resolve against one map.
BASE_ACTIONS = ("view", "create", "edit", "delete", "export")


class PermissionService:
    """A user's effective form permissions = union of their ROLE grants and their
    DIRECT user grants, per form."""

    @staticmethod
    def effective_map(user):
        """-> { form_code: {view,create,edit,delete,export,save,update} }."""
        result = {}

        def bucket(code):
            return result.setdefault(code, {a: False for a in BASE_ACTIONS})

        # Role-based grants (create/edit vocabulary).
        role_ids = UserAccessRepository.role_ids_for_user(user)
        for perm in UserAccessRepository.permissions_for_roles(role_ids):
            b = bucket(perm.form.code)
            b["view"] = b["view"] or perm.can_view
            b["create"] = b["create"] or perm.can_create
            b["edit"] = b["edit"] or perm.can_edit
            b["delete"] = b["delete"] or perm.can_delete
            b["export"] = b["export"] or getattr(perm, "can_export", False)

        # Direct per-user grants (save/update vocabulary -> map onto create/edit).
        for perm in UserAccessRepository.user_permissions(user):
            b = bucket(perm.form.code)
            b["view"] = b["view"] or perm.can_view
            b["create"] = b["create"] or perm.can_save
            b["edit"] = b["edit"] or perm.can_update
            b["delete"] = b["delete"] or perm.can_delete
            b["export"] = b["export"] or perm.can_export

        # Aliases so can(form, "save"/"update") and can(form, "create"/"edit") both work.
        for b in result.values():
            b["save"] = b["create"]
            b["update"] = b["edit"]
        return result

    @staticmethod
    def user_can(user, form_code, action):
        if getattr(user, "is_superuser", False):
            return True
        perms = PermissionService.effective_map(user).get(form_code)
        return bool(perms and perms.get(action))

    @staticmethod
    def visible_columns(user, form_code):
        """-> {column_key: bool} for every active GridColumn registered on
        ``form_code``. A column with no role/user grant rows configured is
        visible to everyone (opt-in gating); once at least one grant exists for
        a column, it becomes an allow-list — only granted roles/users see it.
        Superusers always see every registered column."""
        columns = list(GridColumnRepository.for_form(form_code))
        if not columns:
            return {}

        is_super = getattr(user, "is_superuser", False)
        role_ids = set(UserAccessRepository.role_ids_for_user(user))
        column_ids = [c.id for c in columns]

        gated_ids = set(
            RoleColumnPermission.objects.filter(column_id__in=column_ids)
            .values_list("column_id", flat=True)
        ) | set(
            UserColumnPermission.objects.filter(column_id__in=column_ids)
            .values_list("column_id", flat=True)
        )
        role_granted = set(
            RoleColumnPermission.objects.filter(
                column_id__in=column_ids, role_id__in=role_ids, can_view=True,
            ).values_list("column_id", flat=True)
        ) if role_ids else set()
        user_granted = set(
            UserColumnPermission.objects.filter(
                column_id__in=column_ids, user=user, can_view=True,
            ).values_list("column_id", flat=True)
        )

        result = {}
        for c in columns:
            if is_super or c.id not in gated_ids:
                result[c.key] = True
            else:
                result[c.key] = c.id in role_granted or c.id in user_granted
        return result


class RoleService:
    @staticmethod
    def list(tenant_id):
        return list(RoleRepository.for_tenant(tenant_id))

    @staticmethod
    @transaction.atomic
    def create(tenant_id, *, code, name, description=""):
        code = (code or "").strip().upper()
        if not code:
            raise DomainError("Role code is required.")
        if Role.objects.filter(tenant_id=tenant_id, code=code).exists():
            raise DomainError(f"Role '{code}' already exists.")
        return Role.objects.create(tenant_id=tenant_id, code=code, name=name, description=description)

    @staticmethod
    @transaction.atomic
    def delete(tenant_id, role_id):
        role = RoleRepository.get(tenant_id, role_id)
        if role is None:
            raise DomainError("Role not found.")
        role.ensure_deletable()
        role.delete()

    @staticmethod
    @transaction.atomic
    def set_permission(tenant_id, role_id, form_code, flags):
        role = RoleRepository.get(tenant_id, role_id)
        if role is None:
            raise DomainError("Role not found.")
        form = CatalogueRepository.form_by_code(form_code)
        if form is None:
            raise DomainError(f"Unknown form '{form_code}'.")
        perm, _ = RoleFormPermission.objects.get_or_create(role=role, form=form)
        perm.set_flags(**flags)
        perm.save()
        return perm

    @staticmethod
    @transaction.atomic
    def assign_to_user(tenant_id, user, role_id):
        role = RoleRepository.get(tenant_id, role_id)
        if role is None:
            raise DomainError("Role not found.")
        UserRole.objects.get_or_create(user=user, role=role)

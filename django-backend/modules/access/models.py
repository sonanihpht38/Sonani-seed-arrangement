# ============================ DOMAIN LAYER ============================
# Form-level RBAC — the ERP's access control:
#   ModuleGroup ── has many ── Form            (navigation catalogue)
#   Role ── granted ── RoleFormPermission ── on ── Form   (view/create/edit/delete)
#   User ── assigned ── UserRole ── Role
#
# A "form" is a screen/menu item. Effective permission for a user = the OR of all
# their roles' permissions on that form. Rules (e.g. system roles can't be
# deleted; a granted permission implies view) are enforced here.

from django.conf import settings
from django.db import models

# Canonical DomainError lives in modules.core; re-exported for existing imports.
from modules.core.exceptions import DomainError  # noqa: F401


class ModuleGroup(models.Model):
    """A navigation group, e.g. 'Settings'. Catalogue-level (not tenant-scoped)."""
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=200)
    icon = models.CharField(max_length=60, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "acc_module_group"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.code


class Form(models.Model):
    """A screen/menu item that permissions are granted on."""
    module_group = models.ForeignKey(ModuleGroup, related_name="forms", on_delete=models.CASCADE)
    code = models.CharField(max_length=80, unique=True)      # e.g. 'hr_departments'
    name = models.CharField(max_length=200)
    icon = models.CharField(max_length=60, blank=True)       # react-icons registry key
    route = models.CharField(max_length=200, blank=True)     # frontend path
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "acc_form"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.code


class Role(models.Model):
    tenant = models.ForeignKey(
        "masters.Company", on_delete=models.PROTECT, db_column="tenant_id",
        related_name="+", db_index=True,
    )
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=300, blank=True)
    is_system = models.BooleanField(default=False)           # system roles are protected

    class Meta:
        db_table = "acc_role"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_role_tenant_code"),
        ]

    def __str__(self):
        return self.code

    def ensure_deletable(self):
        if self.is_system:
            raise DomainError("System roles cannot be deleted.")


class UserRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="user_roles", on_delete=models.CASCADE)
    role = models.ForeignKey(Role, related_name="assignments", on_delete=models.CASCADE)

    class Meta:
        db_table = "acc_user_role"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uq_user_role"),
        ]


class RoleFormPermission(models.Model):
    """What a role may do on a form. Absence of a row = no access."""
    role = models.ForeignKey(Role, related_name="form_permissions", on_delete=models.CASCADE)
    form = models.ForeignKey(Form, related_name="role_permissions", on_delete=models.CASCADE)
    can_view = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)

    class Meta:
        db_table = "acc_role_form_permission"
        constraints = [
            models.UniqueConstraint(fields=["role", "form"], name="uq_role_form"),
        ]

    def set_flags(self, *, can_view=None, can_create=None, can_edit=None, can_delete=None, can_export=None):
        if can_view is not None:
            self.can_view = can_view
        if can_create is not None:
            self.can_create = can_create
        if can_edit is not None:
            self.can_edit = can_edit
        if can_delete is not None:
            self.can_delete = can_delete
        if can_export is not None:
            self.can_export = can_export
        # Any write/export capability implies the ability to view the form.
        if self.can_create or self.can_edit or self.can_delete or self.can_export:
            self.can_view = True


class UserFormPermission(models.Model):
    """Direct per-user permission on a form, granted ON TOP OF the user's roles.
    Effective access = union of role permissions and these. Actions:
    view / save (create) / update (edit) / delete / export."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="form_permissions", on_delete=models.CASCADE)
    form = models.ForeignKey(Form, related_name="user_permissions", on_delete=models.CASCADE)
    can_view = models.BooleanField(default=True)
    can_save = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)

    class Meta:
        db_table = "acc_user_form_permission"
        constraints = [
            models.UniqueConstraint(fields=["user", "form"], name="uq_user_form"),
        ]

    def set_flags(self, *, can_view=None, can_save=None, can_update=None, can_delete=None, can_export=None):
        if can_view is not None:
            self.can_view = can_view
        if can_save is not None:
            self.can_save = can_save
        if can_update is not None:
            self.can_update = can_update
        if can_delete is not None:
            self.can_delete = can_delete
        if can_export is not None:
            self.can_export = can_export
        # Any write/export capability implies the ability to view the form.
        if self.can_save or self.can_update or self.can_delete or self.can_export:
            self.can_view = True


# ============================ Column-level RBAC ============================
# Same idea as Form access, one level deeper: a GRID (e.g. the Task List's AG
# Grid) has COLUMNS, and a column can be gated too — e.g. "Priority" only shown
# to roles that should see it. Semantics deliberately mirror Form access:
#   * A column with NO role/user grant rows configured is visible to everyone
#     (opt-in gating — adding masters here never silently breaks a screen).
#   * The moment at least one grant exists for a column, it becomes an
#     allow-list: only users with an explicit grant (via role or direct) see it.
#   * Superusers always see every column, same bypass as HasFormPermission.
class GridColumn(models.Model):
    """The master: which permission-gateable columns exist on a form's grid.
    ``key`` must match the stable colId/field the frontend's ColDef uses."""
    form = models.ForeignKey(Form, related_name="columns", on_delete=models.CASCADE)
    key = models.CharField(max_length=80)      # e.g. 'priority' — matches ColDef colId/field
    label = models.CharField(max_length=200)   # display name in the admin screen
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "acc_grid_column"
        ordering = ["sort_order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["form", "key"], name="uq_grid_column_form_key"),
        ]

    def __str__(self):
        return f"{self.form.code}.{self.key}"


class RoleColumnPermission(models.Model):
    """Whether a role may see a given grid column."""
    role = models.ForeignKey(Role, related_name="column_permissions", on_delete=models.CASCADE)
    column = models.ForeignKey(GridColumn, related_name="role_permissions", on_delete=models.CASCADE)
    can_view = models.BooleanField(default=True)

    class Meta:
        db_table = "acc_role_column_permission"
        constraints = [
            models.UniqueConstraint(fields=["role", "column"], name="uq_role_column"),
        ]


class UserColumnPermission(models.Model):
    """Direct per-user override for a grid column, granted ON TOP OF the user's
    roles. Effective visibility = union of role grants and these."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="column_permissions", on_delete=models.CASCADE)
    column = models.ForeignKey(GridColumn, related_name="user_permissions", on_delete=models.CASCADE)
    can_view = models.BooleanField(default=True)

    class Meta:
        db_table = "acc_user_column_permission"
        constraints = [
            models.UniqueConstraint(fields=["user", "column"], name="uq_user_column"),
        ]

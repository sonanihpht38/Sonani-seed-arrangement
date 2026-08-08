# ===================== ACCOUNTS: identity + tenancy =====================
# The tasks module reads `request.user.tenant_id` and calls `request.user.has_perm(...)`.
# That contract lives here. We extend Django's AbstractUser (which already brings
# the permission system via PermissionsMixin) and add the tenant the user belongs
# to, so every request is naturally tenant-scoped.
#
# RBAC note: `has_perm("tasks.write")` uses Django's built-in permission system.
# A superuser passes every check (handy for the demo). For real roles, create
# Permission rows with codenames like `write`/`assign` and grant them via Groups,
# or swap in a custom backend — the tasks module doesn't change either way.

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # id is an implicit int IDENTITY primary key (DEFAULT_AUTO_FIELD=AutoField).
    # FK to the tenant (nullable: superusers/ops accounts may be tenantless).
    # db_column keeps the existing tenant_id column and .tenant_id call sites.
    tenant = models.ForeignKey(
        "masters.Company", on_delete=models.PROTECT, db_column="tenant_id",
        related_name="+", db_index=True, null=True, blank=True,
    )
    # Self-registered users start unverified (and inactive) until an admin
    # approves them on the User Verification screen. Admin-created users are
    # verified by default.
    is_verified = models.BooleanField(default=True)

    class Meta:
        db_table = "accounts_user"

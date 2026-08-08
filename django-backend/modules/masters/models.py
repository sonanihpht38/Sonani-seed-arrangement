# ============================ DOMAIN LAYER ============================
# Master settings = the tenant's own configuration:
#   1. Company        — the tenant record itself (its id IS the tenant_id).
#   2. SystemSetting  — typed key/value config, per-company or global.
#   3. ParameterType / ParameterValue — generic configurable lookup lists
#      (mst_parameter_type / mst_parameter_value) with audit columns.
#
# All primary keys are int IDENTITY.

from django.db import models

# Canonical DomainError/audit bases live in modules.core; re-exported here.
from modules.core.exceptions import DomainError  # noqa: F401
from modules.core.models import AuditModel


class Company(models.Model):
    """The tenant. Company.id (int) is used as tenant_id everywhere else."""
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    currency_code = models.CharField(max_length=3, default="USD")
    timezone = models.CharField(max_length=64, default="UTC")
    logo_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mst_company"
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    def deactivate(self):
        if not self.is_active:
            return
        self.is_active = False


class SettingValueType(models.TextChoices):
    STRING = "STRING", "String"
    INT = "INT", "Integer"
    BOOL = "BOOL", "Boolean"
    JSON = "JSON", "JSON"


class SystemSetting(models.Model):
    """Typed configuration. tenant NULL = a global/default setting."""
    tenant = models.ForeignKey(
        Company, on_delete=models.PROTECT, db_column="tenant_id",
        related_name="+", db_index=True, null=True, blank=True,
    )
    key = models.CharField(max_length=120)
    value = models.TextField(blank=True)
    value_type = models.CharField(max_length=10, choices=SettingValueType.choices, default=SettingValueType.STRING)
    description = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mst_system_setting"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uq_setting_tenant_key"),
        ]

    def as_python(self):
        """Cast the stored string to its declared type for API responses."""
        if self.value_type == SettingValueType.INT:
            return int(self.value or 0)
        if self.value_type == SettingValueType.BOOL:
            return str(self.value).strip().lower() in ("1", "true", "yes", "on")
        if self.value_type == SettingValueType.JSON:
            import json
            return json.loads(self.value or "null")
        return self.value


class ParameterType(AuditModel):
    """A named lookup category, e.g. 'Departments'. Table: mst_parameter_type.
    Audit columns come from core.AuditModel (the one ERP-wide convention)."""
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(null=True, default=True)

    class Meta:
        db_table = "mst_parameter_type"

    def __str__(self):
        return self.name


class ParameterValue(AuditModel):
    """A value within a ParameterType. Table: mst_parameter_value."""
    parameter_type = models.ForeignKey(
        ParameterType, related_name="values", on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=500)
    short_name = models.CharField(max_length=50, null=True, blank=True)
    sequence_no = models.IntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=500, null=True, blank=True)
    is_active = models.BooleanField(null=True, default=True)

    class Meta:
        db_table = "mst_parameter_value"
        ordering = ["sequence_no", "name"]

    def __str__(self):
        return f"{self.parameter_type.name}:{self.name}"

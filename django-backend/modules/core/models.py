# ===================== SHARED / CROSS-CUTTING: model bases =====================
# The canonical abstract bases every domain module builds on. One audit
# convention, one tenancy convention — module #7 through #100 inherit these
# instead of re-inventing them.

from django.conf import settings
from django.db import models

from .tenancy import TenantManager


class CreatedModel(models.Model):
    """Creation tracking only — for rows created once and never edited
    (references, reminders, transfers)."""

    created_at = models.DateTimeField(auto_now_add=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="+", on_delete=models.SET_NULL, editable=False,
    )

    class Meta:
        abstract = True


class AuditModel(CreatedModel):
    """Full audit columns: created_at/entered_by (inherited) + updated_at/updated_by."""

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="+", on_delete=models.SET_NULL, editable=False,
    )

    class Meta:
        abstract = True


class DocumentSequence(models.Model):
    """Per-tenant document-number counter (see core.sequences.SequenceService)."""

    class Period(models.TextChoices):
        NONE = "NONE", "Continuous"
        YEAR = "YEAR", "Resets yearly"
        MONTH = "MONTH", "Resets monthly"

    tenant = models.ForeignKey(
        "masters.Company", on_delete=models.PROTECT, db_column="tenant_id",
        related_name="+", db_index=True,
    )
    code = models.CharField(max_length=40)           # e.g. "invoice"
    prefix = models.CharField(max_length=20, blank=True)
    padding = models.PositiveSmallIntegerField(default=5)
    period = models.CharField(max_length=8, choices=Period.choices, default=Period.NONE)
    period_key = models.CharField(max_length=10, blank=True, default="")  # "", "2026", "2026-07"
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "core_document_sequence"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code", "period_key"],
                                    name="uq_docseq_tenant_code_period"),
        ]

    def __str__(self):
        return f"{self.code}[{self.period_key or 'ALL'}]={self.next_value}"


class TenantModel(models.Model):
    """A row owned by one tenant (Company). ``objects`` is auto-scoped to the
    current tenant context (see core.tenancy); ``all_objects`` is the explicit
    cross-tenant escape hatch. ``db_column='tenant_id'`` keeps the column name
    every existing table and query already uses."""

    tenant = models.ForeignKey(
        "masters.Company", on_delete=models.PROTECT, db_column="tenant_id",
        related_name="+", db_index=True,
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        # Keep Django's default-manager choice explicit: scoped by default.
        default_manager_name = "objects"
        base_manager_name = "all_objects"

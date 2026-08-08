# Step 1 of the masters audit convergence: add the canonical AuditModel columns
# (created_at/entered_by/updated_at/updated_by) alongside the legacy
# entry_*/update_* columns and copy the data across. The legacy columns are
# dropped in 0005 (kept separate so it can be deferred if any external SQL
# still reads them).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F
from django.db.models.functions import Now


def copy_audit(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    valid_user_ids = list(User.objects.values_list("id", flat=True))
    for model_name in ("ParameterType", "ParameterValue"):
        M = apps.get_model("masters", model_name)
        # .update() bypasses auto_now/auto_now_add, so the copied values stick.
        M.objects.update(created_at=F("entry_date"), updated_at=F("update_date"))
        M.objects.filter(created_at__isnull=True).update(created_at=Now())
        M.objects.filter(updated_at__isnull=True).update(updated_at=F("created_at"))
        M.objects.filter(entry_by__in=valid_user_ids).update(entered_by_id=F("entry_by"))
        M.objects.filter(update_by__in=valid_user_ids).update(updated_by_id=F("update_by"))


def uncopy_audit(apps, schema_editor):
    pass  # columns are simply dropped on reverse


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0003_tenant_fk"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Nullable first; 0005 tightens created_at/updated_at to the canonical
        # non-null definitions once every row has a value.
        migrations.AddField("parametertype", "created_at", models.DateTimeField(null=True)),
        migrations.AddField("parametertype", "updated_at", models.DateTimeField(null=True)),
        migrations.AddField(
            "parametertype", "entered_by",
            models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="+",
                              on_delete=django.db.models.deletion.SET_NULL, editable=False),
        ),
        migrations.AddField(
            "parametertype", "updated_by",
            models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="+",
                              on_delete=django.db.models.deletion.SET_NULL, editable=False),
        ),
        migrations.AddField("parametervalue", "created_at", models.DateTimeField(null=True)),
        migrations.AddField("parametervalue", "updated_at", models.DateTimeField(null=True)),
        migrations.AddField(
            "parametervalue", "entered_by",
            models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="+",
                              on_delete=django.db.models.deletion.SET_NULL, editable=False),
        ),
        migrations.AddField(
            "parametervalue", "updated_by",
            models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="+",
                              on_delete=django.db.models.deletion.SET_NULL, editable=False),
        ),
        migrations.RunPython(copy_audit, uncopy_audit),
    ]

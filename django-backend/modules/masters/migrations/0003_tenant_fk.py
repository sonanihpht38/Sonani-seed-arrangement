# SystemSetting.tenant_id (int, nullable) -> FK(Company) keeping the column.
# uq_setting_tenant_key covers the same columns; only its state changes.

import django.db.models.deletion
from django.db import migrations, models

from modules.core.migration_utils import add_tenant_fk

_fwd, _bwd = add_tenant_fk("mst_system_setting")


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0002_alter_parametertype_entry_by_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(model_name="systemsetting", name="uq_setting_tenant_key"),
                migrations.RemoveField(model_name="systemsetting", name="tenant_id"),
                migrations.AddField(
                    model_name="systemsetting",
                    name="tenant",
                    field=models.ForeignKey(
                        "masters.Company", on_delete=django.db.models.deletion.PROTECT,
                        db_column="tenant_id", related_name="+", db_index=True,
                        null=True, blank=True,
                    ),
                ),
                migrations.AddConstraint(
                    model_name="systemsetting",
                    constraint=models.UniqueConstraint(
                        fields=["tenant", "key"], name="uq_setting_tenant_key",
                    ),
                ),
            ],
            database_operations=[migrations.RunPython(_fwd, _bwd)],
        ),
    ]

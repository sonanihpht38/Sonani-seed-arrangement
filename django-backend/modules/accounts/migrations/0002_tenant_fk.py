# tenant_id (int, nullable) -> FK(masters.Company) keeping the tenant_id column.

import django.db.models.deletion
from django.db import migrations, models

from modules.core.migration_utils import add_tenant_fk

_fwd, _bwd = add_tenant_fk("accounts_user")


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0002_alter_parametertype_entry_by_and_more"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="user", name="tenant_id"),
                migrations.AddField(
                    model_name="user",
                    name="tenant",
                    field=models.ForeignKey(
                        "masters.Company", on_delete=django.db.models.deletion.PROTECT,
                        db_column="tenant_id", related_name="+", db_index=True,
                        null=True, blank=True,
                    ),
                ),
            ],
            database_operations=[migrations.RunPython(_fwd, _bwd)],
        ),
    ]

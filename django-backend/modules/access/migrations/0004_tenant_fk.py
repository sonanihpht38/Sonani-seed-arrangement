# Role.tenant_id (int) -> FK(masters.Company) keeping the tenant_id column.
# The uq_role_tenant_code unique constraint covers the same columns, so only
# its state definition changes.

import django.db.models.deletion
from django.db import migrations, models

from modules.core.migration_utils import add_tenant_fk

_fwd, _bwd = add_tenant_fk("acc_role")


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0002_alter_parametertype_entry_by_and_more"),
        ("access", "0003_gridcolumn_rolecolumnpermission_usercolumnpermission_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(model_name="role", name="uq_role_tenant_code"),
                migrations.RemoveField(model_name="role", name="tenant_id"),
                migrations.AddField(
                    model_name="role",
                    name="tenant",
                    field=models.ForeignKey(
                        "masters.Company", on_delete=django.db.models.deletion.PROTECT,
                        db_column="tenant_id", related_name="+", db_index=True,
                    ),
                ),
                migrations.AddConstraint(
                    model_name="role",
                    constraint=models.UniqueConstraint(
                        fields=["tenant", "code"], name="uq_role_tenant_code",
                    ),
                ),
            ],
            database_operations=[migrations.RunPython(_fwd, _bwd)],
        ),
    ]

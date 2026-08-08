# Step 2 of the masters audit convergence: tighten created_at/updated_at to the
# canonical AuditModel definitions and DROP the legacy entry_*/update_* columns.
# Deliberately separate from 0004 — defer this one if any external SQL/report
# still reads the old columns.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0004_param_audit_converge"),
    ]

    operations = [
        migrations.AlterField("parametertype", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("parametertype", "updated_at", models.DateTimeField(auto_now=True)),
        migrations.AlterField("parametervalue", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("parametervalue", "updated_at", models.DateTimeField(auto_now=True)),
        migrations.RemoveField("parametertype", "entry_date"),
        migrations.RemoveField("parametertype", "entry_by"),
        migrations.RemoveField("parametertype", "entry_ip"),
        migrations.RemoveField("parametertype", "update_date"),
        migrations.RemoveField("parametertype", "update_by"),
        migrations.RemoveField("parametertype", "update_ip"),
        migrations.RemoveField("parametervalue", "entry_date"),
        migrations.RemoveField("parametervalue", "entry_by"),
        migrations.RemoveField("parametervalue", "entry_ip"),
        migrations.RemoveField("parametervalue", "update_date"),
        migrations.RemoveField("parametervalue", "update_by"),
        migrations.RemoveField("parametervalue", "update_ip"),
    ]

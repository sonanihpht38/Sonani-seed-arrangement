# Helpers for the tenant_id -> FK conversion migrations.
#
# The int tenant_id columns already exist with the right type and index, so the
# only real database work is adding the FK constraint. Each app's migration
# swaps the field in Django's state via SeparateDatabaseAndState and calls
# add_tenant_fk() as its only database operation.


def add_tenant_fk(table, *, constraint=None):
    """Build a RunPython pair that adds/drops FK <table>.tenant_id -> mst_company(id).

    - Pre-checks for orphan tenant ids and fails with a clear message (SQL
      Server's WITH CHECK would also fail, but cryptically).
    - No-ops on non-mssql engines (sqlite dev DBs don't enforce the FK; the
      Django state still has it, which is what matters for the ORM).
    """
    constraint = constraint or f"fk_{table}_tenant"

    def forwards(apps, schema_editor):
        if schema_editor.connection.vendor != "microsoft":
            return
        with schema_editor.connection.cursor() as c:
            c.execute(
                f"SELECT COUNT(*) FROM [{table}] t WHERE t.[tenant_id] IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM [mst_company] m WHERE m.[id] = t.[tenant_id])"
            )
            orphans = c.fetchone()[0]
        if orphans:
            raise RuntimeError(
                f"{table}: {orphans} row(s) reference a tenant_id with no mst_company row. "
                f"Fix the data before adding the FK constraint."
            )
        schema_editor.execute(
            f"ALTER TABLE [{table}] WITH CHECK ADD CONSTRAINT [{constraint}] "
            f"FOREIGN KEY ([tenant_id]) REFERENCES [mst_company] ([id])"
        )

    def backwards(apps, schema_editor):
        if schema_editor.connection.vendor != "microsoft":
            return
        schema_editor.execute(f"ALTER TABLE [{table}] DROP CONSTRAINT [{constraint}]")

    return forwards, backwards

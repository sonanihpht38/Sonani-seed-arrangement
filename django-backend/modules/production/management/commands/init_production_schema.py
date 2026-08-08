"""Create the production module's tables on the `default` connection.

The production models are `managed = False` (Django never creates them), so this
command — not a migration — owns their schema. The DDL in `modules/production/sql/`
is idempotent (`IF OBJECT_ID(...) IS NULL`), so running it twice is a no-op.

    python manage.py init_production_schema           # create what's missing
    python manage.py init_production_schema --check   # report only, exit 1 if missing

SQL Server only: the scripts use `uniqueidentifier`, `datetime2` and `GO` batch
separators. On sqlite (local dev without a DB) the command exits with a notice
rather than pretending to succeed.
"""

import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
SCRIPTS = ["create_seed_tables.sql", "create_arrange_tables.sql"]

TABLES = [
    "TRN_Batch", "TRN_SeedData", "TRN_DummySeedData", "TRN_SeedArrange",
    "MST_SeedPlate", "TRN_SeedPlate", "TRN_SeedArrangeDetails",
]

# `GO` is a client-side batch separator (sqlcmd/SSMS), not a T-SQL statement —
# a DB-API cursor rejects it, so split the script on it and execute each batch.
_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)


def _batches(sql):
    return [b.strip() for b in _GO.split(sql) if b.strip()]


class Command(BaseCommand):
    help = "Create the production module's (managed=False) tables from sql/*.sql."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true",
                            help="Report which tables are missing; write nothing.")

    def _missing(self):
        with connection.cursor() as c:
            missing = []
            for t in TABLES:
                c.execute("SELECT OBJECT_ID(%s, 'U')", [f"dbo.{t}"])
                if c.fetchone()[0] is None:
                    missing.append(t)
        return missing

    def handle(self, *args, **options):
        if connection.vendor != "microsoft":
            self.stderr.write(self.style.WARNING(
                f"Skipped: the production schema is SQL Server DDL and this "
                f"connection is '{connection.vendor}'."
            ))
            return

        missing = self._missing()
        if options["check"]:
            if missing:
                self.stderr.write(self.style.ERROR(f"Missing tables: {', '.join(missing)}"))
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS("Production schema present — all 7 tables exist."))
            return

        # Always run both scripts, even when every table exists: besides the
        # CREATEs they carry guarded ALTERs that back-fill columns added after a
        # database was first created. Every statement is individually guarded.
        self.stdout.write("Creating: " + (", ".join(missing) if missing else "nothing (applying column back-fill)"))
        with connection.cursor() as c:
            for name in SCRIPTS:
                for batch in _batches((SQL_DIR / name).read_text(encoding="utf-8")):
                    c.execute(batch)

        still = self._missing()
        if still:
            self.stderr.write(self.style.ERROR(f"Still missing after DDL: {', '.join(still)}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"Production schema ready ({len(TABLES)} tables)."))

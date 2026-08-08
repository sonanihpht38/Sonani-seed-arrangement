"""Ensure a ready-to-assign role that grants the whole production workflow.

Self-registration (RegistrationService) auto-assigns "Production User" so a new
account can use the app immediately; an admin can also assign it by hand in the
Django admin (User roles → Add). This command creates/refreshes that role and its
permissions, idempotently, so it's safe to run on every deploy.

    python manage.py ensure_production_role

It also refreshes the legacy MANAGER role onto the same production screens — its
old grants pointed at modules that were removed, so any account holding it saw
"No access" until now.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from modules.access.models import Role
from modules.access.services import RoleService
from modules.masters.models import Company

# The nine production forms, in workflow order. Codes match production/catalogue.py.
PRODUCTION_FORMS = [
    "seed_import", "batch_selection", "criteria_input", "processing_option",
    "result_generation", "finalization", "download", "arrangement_history",
    "plate_master",
]

FULL = {"can_view": True, "can_create": True, "can_edit": True,
        "can_delete": True, "can_export": True}

# code -> display name. MANAGER is refreshed in place; PRODUCTION_USER is the
# canonical role self-registration hands out.
ROLES = {
    "PRODUCTION_USER": "Production User",
    "MANAGER": "Manager",
}


class Command(BaseCommand):
    help = "Create/refresh the Production User (and MANAGER) role with full production access."

    @transaction.atomic
    def handle(self, *args, **options):
        company = Company.objects.first()
        if company is None:
            self.stderr.write(self.style.ERROR("No Company exists — run seed_demo (or create a company) first."))
            raise SystemExit(1)
        tenant = company.id

        for code, name in ROLES.items():
            role, created = Role.objects.get_or_create(
                tenant_id=tenant, code=code,
                defaults={"name": name, "description": "Full access to the production workflow"},
            )
            for form_code in PRODUCTION_FORMS:
                RoleService.set_permission(tenant, role.id, form_code, FULL)
            verb = "created" if created else "refreshed"
            self.stdout.write(self.style.SUCCESS(
                f"  {verb} role {code} ({name}) — {len(PRODUCTION_FORMS)} production forms granted"
            ))

        self.stdout.write(self.style.SUCCESS("Production roles ready."))

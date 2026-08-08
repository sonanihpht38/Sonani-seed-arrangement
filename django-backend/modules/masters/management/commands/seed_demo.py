# Idempotent DEMO DATA seed: a demo company, users, a role, and settings. Run:
#   python manage.py seed_demo
#
# The form/menu/grid-column catalogue is NOT declared here — each module ships a
# catalogue.py and `sync_catalogue` (called first below) upserts them. This
# command only owns demo *data*.

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from modules.access.models import Role, UserRole
from modules.access.services import RoleService
from modules.masters.models import Company, ParameterType, ParameterValue, SystemSetting
from modules.notifications.models import Notification

User = get_user_model()

ADMIN = ("admin", "admin123")
MANAGER = ("manager", "manager123")

# The production workflow, in the order an operator walks it.
PRODUCTION_FORMS = [
    "seed_import", "batch_selection", "criteria_input", "processing_option",
    "result_generation", "finalization", "download", "arrangement_history",
    "plate_master",
]


class Command(BaseCommand):
    help = "Seed the catalogue + a demo company, users, role and sample data (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("sync_catalogue")

        company, _ = Company.objects.get_or_create(
            code="ACME",
            defaults={"name": "Acme Corp", "currency_code": "USD", "timezone": "UTC"},
        )
        tenant = company.id

        admin = self._ensure_user(ADMIN, tenant, is_superuser=True, is_staff=True)
        manager = self._ensure_user(MANAGER, tenant, is_superuser=False, is_staff=False)

        role, _ = Role.objects.get_or_create(
            tenant_id=tenant, code="MANAGER",
            defaults={"name": "Manager", "description": "Runs the plate-arrangement workflow"},
        )
        full = {"can_view": True, "can_create": True, "can_edit": True,
                "can_delete": True, "can_export": True}
        for f in PRODUCTION_FORMS:
            RoleService.set_permission(tenant, role.id, f, full)
        UserRole.objects.get_or_create(user=manager, role=role)

        SystemSetting.objects.get_or_create(
            tenant_id=tenant, key="invoice_prefix",
            defaults={"value": "INV", "value_type": "STRING", "description": "Invoice number prefix"},
        )
        SystemSetting.objects.get_or_create(
            tenant_id=tenant, key="fiscal_year_start_month",
            defaults={"value": "4", "value_type": "INT", "description": "Fiscal year start month"},
        )

        dept, _ = ParameterType.objects.get_or_create(name="Departments", defaults={"is_active": True})
        for order, (short, label) in enumerate([("ENG", "Engineering"), ("FIN", "Finance"), ("HR", "Human Resources")]):
            ParameterValue.objects.get_or_create(
                parameter_type=dept, name=label,
                defaults={"short_name": short, "sequence_no": order, "is_active": True},
            )

        # A couple of sample notifications for the admin's bell.
        if not Notification.objects.filter(user=admin).exists():
            Notification.notify(admin, "Welcome to Sonani Seed Arrangement", "Your account is ready. Start from Seed Import in the sidebar.", "success")
            Notification.notify(admin, "Backup completed", "Nightly database backup finished successfully.", "info")

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  Company : {company.name} ({company.code})  tenant={tenant}")
        self.stdout.write(f"  Admin   : {ADMIN[0]} / {ADMIN[1]}   (superuser)")
        self.stdout.write(f"  Manager : {MANAGER[0]} / {MANAGER[1]} (role MANAGER — full production access)")

    def _ensure_user(self, creds, tenant, **flags):
        username, password = creds
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User(username=username, email=f"{username}@acme.test", tenant_id=tenant, **flags)
        else:
            user.tenant_id = tenant
            for k, v in flags.items():
                setattr(user, k, v)
        user.set_password(password)
        user.save()
        return user

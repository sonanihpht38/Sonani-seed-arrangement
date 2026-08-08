# ===================== SHARED / CROSS-CUTTING: test kit =====================
# Dependency-free helpers (plain Django TestCase + DRF test client) plus the
# per-module CONTRACT TEST every TenantCrudViewSet module inherits:
#
#     class DepartmentContractTests(CrudContractTestMixin, TestCase):
#         base_url = "/api/hr/departments/"
#         form_code = "hr_departments"
#         def make_instance(self, tenant, **kw):
#             return Department.objects.create(tenant_id=tenant.id, name="X", **kw)
#         def create_payload(self):
#             return {"name": "New row"}
#
# The mixin asserts: 401 anon, 403 without the form grant, envelope list shape,
# and (for tenant models) cross-tenant isolation. Modules get this for free
# from the startmodule scaffold.

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from modules.access.models import Role, UserRole
from modules.access.services import RoleService
from modules.masters.models import Company

User = get_user_model()

FULL = {"can_view": True, "can_create": True, "can_edit": True,
        "can_delete": True, "can_export": True}


def make_company(code="T1", name="Tenant One"):
    return Company.objects.create(code=code, name=name)


def make_user(username, tenant=None, superuser=False, password="pw"):
    user = User(username=username, tenant_id=tenant.id if tenant else None,
                is_superuser=superuser, is_staff=superuser)
    user.set_password(password)
    user.save()
    return user


def grant(user, form_code, flags=None):
    """Grant form permissions to a user through a per-user role."""
    role, _ = Role.objects.get_or_create(
        tenant_id=user.tenant_id, code=f"TEST_{user.username}".upper()[:60],
        defaults={"name": f"Test role for {user.username}"},
    )
    RoleService.set_permission(user.tenant_id, role.id, form_code, flags or FULL)
    UserRole.objects.get_or_create(user=user, role=role)
    return role


def api_client(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


class CrudContractTestMixin:
    """The module contract. Subclass with TestCase and fill the three hooks."""

    base_url = None          # e.g. "/api/hr/departments/"
    form_code = None         # e.g. "hr_departments"
    tenant_scoped = True     # False for global lookup resources

    # -- hooks -----------------------------------------------------------------
    def make_instance(self, tenant, **kwargs):
        raise NotImplementedError

    def create_payload(self):
        raise NotImplementedError

    # -- fixtures ----------------------------------------------------------------
    @classmethod
    def setUpTestData(cls):
        # Also proves the module's catalogue registers cleanly — a form_code
        # typo in the viewset or catalogue fails here, not in production.
        call_command("sync_catalogue", verbosity=0)
        cls.tenant_a = make_company("TA", "Tenant A")
        cls.tenant_b = make_company("TB", "Tenant B")
        cls.user_a = make_user("contract_a", cls.tenant_a)
        cls.user_b = make_user("contract_b", cls.tenant_b)
        cls.user_noperm = make_user("contract_noperm", cls.tenant_a)

    def setUp(self):
        grant(self.user_a, self.form_code)
        grant(self.user_b, self.form_code)

    # -- the contract -----------------------------------------------------------
    def test_anonymous_is_401(self):
        res = APIClient().get(self.base_url)
        self.assertEqual(res.status_code, 401)

    def test_without_form_grant_is_403(self):
        res = api_client(self.user_noperm).get(self.base_url)
        self.assertEqual(res.status_code, 403)

    def test_list_returns_standard_envelope(self):
        self.make_instance(self.tenant_a)
        res = api_client(self.user_a).get(self.base_url)
        self.assertEqual(res.status_code, 200)
        for key in ("results", "total", "page", "page_size", "total_pages"):
            self.assertIn(key, res.data)
        self.assertGreaterEqual(res.data["total"], 1)

    def test_create_succeeds_with_grant(self):
        res = api_client(self.user_a).post(self.base_url, self.create_payload(), format="json")
        self.assertEqual(res.status_code, 201, res.data)

    def test_export_csv_streams_with_grant(self):
        self.make_instance(self.tenant_a)
        res = api_client(self.user_a).get(f"{self.base_url}export/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res["Content-Type"].startswith("text/csv"))
        body = b"".join(res.streaming_content).decode("utf-8")
        self.assertGreaterEqual(len(body.strip().splitlines()), 2)  # header + >=1 row

    def test_import_csv_dry_run_validates(self):
        import io

        payload = self.create_payload()
        keys = list(payload.keys())
        csv_text = ",".join(keys) + "\n" + ",".join(str(payload[k]) for k in keys) + "\n"
        upload = io.BytesIO(csv_text.encode("utf-8"))
        upload.name = "rows.csv"
        res = api_client(self.user_a).post(f"{self.base_url}import/?dry_run=1",
                                           {"file": upload}, format="multipart")
        self.assertEqual(res.status_code, 200, getattr(res, "data", None))
        self.assertEqual(res.data["valid"], 1, res.data)
        self.assertTrue(res.data["dry_run"])

    def test_tenant_isolation(self):
        if not self.tenant_scoped:
            self.skipTest("global (non-tenant) resource")
        mine = self.make_instance(self.tenant_a)
        self.make_instance(self.tenant_b)
        res = api_client(self.user_a).get(self.base_url)
        self.assertEqual(res.status_code, 200)
        ids = [row["id"] for row in res.data["results"]]
        self.assertIn(mine.id, ids)
        # Nothing from tenant B may leak into tenant A's list.
        other = api_client(self.user_b).get(self.base_url)
        other_ids = {row["id"] for row in other.data["results"]}
        self.assertFalse(set(ids) & other_ids, "cross-tenant rows leaked")

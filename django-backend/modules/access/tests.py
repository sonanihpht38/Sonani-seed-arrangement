# Unit tests for the RBAC core. PermissionService is the single source of truth
# for "what can this user do", so it gets the most coverage: the union across
# roles, the superuser bypass, denial when no roles/permissions exist, and
# rejection of unknown actions.

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from modules.masters.models import Company

from .models import Form, ModuleGroup, Role, RoleFormPermission, UserRole
from .services import PermissionService, RoleService

User = get_user_model()


class PermissionServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # tenant_id is a real FK to mst_company now — use an actual Company id.
        cls.tenant = Company.objects.create(code="T-PERM", name="Perm Tenant").id
        group = ModuleGroup.objects.create(code="SETTINGS", name="Settings")
        cls.form = Form.objects.create(module_group=group, code="company_settings", name="Company Settings")
        cls.other_form = Form.objects.create(module_group=group, code="api_management", name="API Management")

    def _user(self, **kwargs):
        u = User(username=f"u{uuid.uuid4().hex[:8]}", tenant_id=self.tenant, **kwargs)
        u.set_password("x")
        u.save()
        return u

    def _role_with(self, **flags):
        role = Role.objects.create(tenant_id=self.tenant, code=f"R{uuid.uuid4().hex[:6]}", name="R")
        RoleFormPermission.objects.create(role=role, form=self.form, **flags)
        return role

    def test_superuser_bypasses_all_checks(self):
        admin = self._user(is_superuser=True)
        self.assertTrue(PermissionService.user_can(admin, "company_settings", "delete"))
        self.assertTrue(PermissionService.user_can(admin, "anything", "edit"))

    def test_user_with_no_roles_has_no_access(self):
        user = self._user()
        self.assertEqual(PermissionService.effective_map(user), {})
        self.assertFalse(PermissionService.user_can(user, "company_settings", "view"))

    def test_single_role_grants_declared_flags_only(self):
        user = self._user()
        role = self._role_with(can_view=True, can_edit=True)
        UserRole.objects.create(user=user, role=role)

        self.assertTrue(PermissionService.user_can(user, "company_settings", "view"))
        self.assertTrue(PermissionService.user_can(user, "company_settings", "edit"))
        self.assertFalse(PermissionService.user_can(user, "company_settings", "delete"))
        self.assertFalse(PermissionService.user_can(user, "company_settings", "create"))

    def test_permissions_union_across_multiple_roles(self):
        user = self._user()
        r1 = self._role_with(can_view=True, can_edit=True)
        r2 = self._role_with(can_view=True, can_delete=True)
        UserRole.objects.create(user=user, role=r1)
        UserRole.objects.create(user=user, role=r2)

        perms = PermissionService.effective_map(user)["company_settings"]
        self.assertTrue(perms["edit"])
        self.assertTrue(perms["delete"])
        self.assertTrue(PermissionService.user_can(user, "company_settings", "edit"))
        self.assertTrue(PermissionService.user_can(user, "company_settings", "delete"))

    def test_unknown_action_is_denied_for_normal_user(self):
        user = self._user()
        role = self._role_with(can_view=True)
        UserRole.objects.create(user=user, role=role)
        self.assertFalse(PermissionService.user_can(user, "company_settings", "frobnicate"))

    def test_no_access_to_unrelated_form(self):
        user = self._user()
        role = self._role_with(can_view=True, can_edit=True)
        UserRole.objects.create(user=user, role=role)
        self.assertFalse(PermissionService.user_can(user, "api_management", "view"))


class RoleServiceTests(TestCase):
    def setUp(self):
        self.tenant = Company.objects.create(code=f"T{uuid.uuid4().hex[:6]}", name="Role Tenant").id
        group = ModuleGroup.objects.create(code="SETTINGS", name="Settings")
        Form.objects.create(module_group=group, code="company_settings", name="Company Settings")

    def test_set_permission_implies_view(self):
        role = RoleService.create(self.tenant, code="mgr", name="Manager")
        RoleService.set_permission(self.tenant, role.id, "company_settings", {"can_edit": True})
        perm = RoleFormPermission.objects.get(role=role, form__code="company_settings")
        self.assertTrue(perm.can_edit)
        self.assertTrue(perm.can_view)  # write capability implies view

    def test_system_role_cannot_be_deleted(self):
        role = Role.objects.create(tenant_id=self.tenant, code="SYS", name="System", is_system=True)
        from .models import DomainError
        with self.assertRaises(DomainError):
            RoleService.delete(self.tenant, role.id)

    def test_duplicate_role_code_rejected(self):
        RoleService.create(self.tenant, code="dup", name="One")
        from .models import DomainError
        with self.assertRaises(DomainError):
            RoleService.create(self.tenant, code="DUP", name="Two")

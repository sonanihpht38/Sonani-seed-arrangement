# ===================== SHARED / CROSS-CUTTING: RBAC =====================
# The DRF permission class every module reuses for form-level checks. Backed by
# PermissionService so the rule ("can this user do X on form Y") lives in ONE
# place. Usage:
#     permission_classes = [HasFormPermission.require("hr_departments", "edit")]

from rest_framework.permissions import BasePermission

from .services import PermissionService


class HasFormPermission(BasePermission):
    form_code = None
    action = "view"

    message = "You do not have permission for this form."

    @classmethod
    def require(cls, form_code, action="view"):
        return type(
            "HasFormPermission",
            (cls,),
            {"form_code": form_code, "action": action},
        )

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return PermissionService.user_can(user, self.form_code, self.action)

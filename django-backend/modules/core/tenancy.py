# ===================== SHARED / CROSS-CUTTING: tenancy =====================
# Tenant scoping as an opt-OUT instead of opt-in.
#
# The current tenant lives in a ContextVar. It is set:
#   * per API request by TenantCrudViewSet.initial() (DRF authenticates at the
#     view layer, so Django middleware cannot see JWT users — the viewset hook
#     is the deterministic place);
#   * per background job by wrapping work in ``with tenant_context(tid): ...``
#     (Celery tasks and management commands MUST do this, or queries through
#     TenantManager run unscoped).
#
# Models that inherit TenantModel get ``objects`` filtered to the current
# tenant whenever the context is set, and ``all_objects`` as the explicit
# cross-tenant escape hatch (admin, reports, seeds).

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import models

_current_tenant: ContextVar = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id):
    _current_tenant.set(tenant_id)


def get_current_tenant():
    return _current_tenant.get()


@contextmanager
def tenant_context(tenant_id):
    token = _current_tenant.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant.reset(token)


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant_id):
        return self.filter(tenant_id=tenant_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Default manager for TenantModel: auto-filters by the ContextVar tenant.

    When no tenant context is set (shell, unscoped job) it returns everything —
    the contract tests assert API requests always run scoped.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = get_current_tenant()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        return qs


class TenantContextMiddleware:
    """Best-effort tenant context for session-authenticated requests (Django
    admin). JWT API requests are covered by TenantCrudViewSet.initial()."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        tenant_id = getattr(user, "tenant_id", None) if user and user.is_authenticated else None
        token = _current_tenant.set(tenant_id)
        try:
            return self.get_response(request)
        finally:
            _current_tenant.reset(token)

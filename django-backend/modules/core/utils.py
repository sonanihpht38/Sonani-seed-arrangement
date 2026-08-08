# ===================== SHARED / CROSS-CUTTING: small helpers =====================


def tenant_of(request):
    """The requesting user's tenant id (Company pk)."""
    return request.user.tenant_id


def is_admin(user):
    """The 'admin bypass' used by per-actor domain guards."""
    return bool(getattr(user, "is_superuser", False))


def client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")

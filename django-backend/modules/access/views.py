# ============================= API LAYER =============================
# What the running app reads from the RBAC engine: the navigation catalogue that
# builds the sidebar, and the current user's grid-column visibility. Roles,
# form permissions and the form catalogue itself are no longer editable over the
# API — they are seeded (`sync_catalogue`, `seed_demo`) and maintained from the
# Django admin. Enforcement is unchanged: HasFormPermission still gates every
# module's viewsets.

from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .repository import CatalogueRepository
from .serializers import ModuleGroupSerializer
from .services import PermissionService


class CatalogueViewSet(viewsets.ViewSet):
    """Read-only navigation catalogue: module groups and their forms."""
    permission_classes = [IsAuthenticated]

    def list(self, request):
        groups = CatalogueRepository.groups()
        return Response(ModuleGroupSerializer(groups, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def visible_columns(request):
    """GET /access/visible-columns/?form=<code> -> {column_key: bool} for the
    CURRENT user. Any grid can call this to decide which of its columns to
    render; a key absent from the response means that column isn't managed by
    this system at all and should always show."""
    form_code = request.query_params.get("form")
    if not form_code:
        return Response({"detail": "form is required."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(PermissionService.visible_columns(request.user, form_code))

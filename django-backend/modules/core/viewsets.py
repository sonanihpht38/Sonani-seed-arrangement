# ===================== SHARED / CROSS-CUTTING: base viewsets =====================
# The CRUD contract for module #7 and beyond. A module's viewset is:
#
#     class LeaveRequestViewSet(TenantCrudViewSet):
#         form_code = "leave_request"
#         queryset = LeaveRequest.objects.all()
#         serializer_class = LeaveRequestSerializer
#         search_fields = ["employee__name", "reason"]
#
# and gets: form-level RBAC on every action, tenant scoping, ownership stamping
# (entered_by/updated_by + tenant on create), CSV export/import endpoints, and
# the standard {results,total,page,page_size,total_pages} list envelope.
#
# There is no global change-history row: the audit module was removed. Each model
# still carries entered_by/updated_by, so *who last touched a row* survives —
# but not *what changed*.

import csv
import io

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.access.permissions import HasFormPermission
from modules.core.pagination import page_params, paginate_envelope
from modules.core.tenancy import set_current_tenant


class TenantCrudViewSet(viewsets.ModelViewSet):
    #: RBAC form code — REQUIRED. Every action maps to a form action below.
    form_code = None
    #: Override per-viewset for custom @actions (defaults custom actions to "edit").
    action_perm_map = {
        "list": "view", "retrieve": "view", "create": "create",
        "update": "edit", "partial_update": "edit", "destroy": "delete",
        "export_csv": "export", "import_csv": "create",
    }
    #: DRF's paginator is unused — list() returns the envelope. Kept None so the
    #: pagination behavior of all modules stays uniform.
    pagination_class = None
    #: Envelope page-size cap (see core.pagination.page_params).
    max_page_size = 100
    #: Row cap for CSV export (streams the full filtered queryset up to this).
    export_max_rows = 100_000

    # -- auth / scoping --------------------------------------------------------
    def initial(self, request, *args, **kwargs):
        # DRF authenticates at the view layer (JWT), so this — not Django
        # middleware — is where the tenant context becomes known.
        super().initial(request, *args, **kwargs)
        if request.user and request.user.is_authenticated:
            set_current_tenant(request.user.tenant_id)

    def get_permissions(self):
        assert self.form_code, f"{type(self).__name__} must set form_code"
        act = self.action_perm_map.get(self.action, "edit")
        return [HasFormPermission.require(self.form_code, act)()]

    def get_queryset(self):
        # EXPLICIT tenant filter at request time. A class-level
        # `queryset = Model.objects.all()` was built at import time — before any
        # tenant context — so the manager's ContextVar scoping never applied to
        # it. Filtering here is deterministic for every request. A tenantless
        # user (ops superuser) sees across tenants.
        qs = super().get_queryset()
        if "tenant" in {f.name for f in qs.model._meta.get_fields()}:
            tenant_id = getattr(self.request.user, "tenant_id", None)
            if tenant_id is not None:
                qs = qs.filter(tenant_id=tenant_id)
        return qs

    # -- ownership stamping -------------------------------------------------------
    def perform_create(self, serializer):
        extra = {}
        model = serializer.Meta.model
        field_names = {f.name for f in model._meta.get_fields()}
        if "tenant" in field_names:
            extra["tenant_id"] = self.request.user.tenant_id
        if "entered_by" in field_names:
            extra["entered_by"] = self.request.user
        if "updated_by" in field_names:
            extra["updated_by"] = self.request.user
        serializer.save(**extra)

    def perform_update(self, serializer):
        extra = {}
        if "updated_by" in {f.name for f in serializer.Meta.model._meta.get_fields()}:
            extra["updated_by"] = self.request.user
        serializer.save(**extra)

    # -- standard envelope list -------------------------------------------------
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page, page_size = page_params(request, max_size=self.max_page_size)
        total = qs.count()
        start = (page - 1) * page_size
        serializer = self.get_serializer(qs[start:start + page_size], many=True)
        return Response(paginate_envelope(serializer.data, total, page, page_size))

    # -- CSV export / import ------------------------------------------------------
    def _csv_fields(self):
        """Scalar serializer fields (nested collections are skipped) for CSV columns."""
        from rest_framework import serializers as drf

        ser = self.get_serializer_class()()
        return [name for name, field in ser.fields.items()
                if not isinstance(field, (drf.BaseSerializer, drf.ListField, drf.DictField))]

    @action(detail=False, methods=["get"], url_path="export")
    def export_csv(self, request):
        """Stream the FULL filtered queryset as CSV (gated on can_export)."""
        from django.http import StreamingHttpResponse

        qs = self.filter_queryset(self.get_queryset())[: self.export_max_rows]
        fields = self._csv_fields()

        def rows():
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(fields)
            yield buf.getvalue()
            for obj in qs.iterator():
                buf.seek(0); buf.truncate()
                data = self.get_serializer(obj).data
                writer.writerow([_csv_cell(data.get(f)) for f in fields])
                yield buf.getvalue()

        resp = StreamingHttpResponse(rows(), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{self.form_code}.csv"'
        return resp

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        """Two-step CSV import: ?dry_run=1 (default) validates and reports
        row-level errors; dry_run=0 commits atomically (all rows or none)."""
        from django.db import transaction

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Upload a CSV as form field 'file'."},
                            status=status.HTTP_400_BAD_REQUEST)
        dry_run = request.query_params.get("dry_run", "1") not in ("0", "false")
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"detail": "File must be UTF-8 CSV."},
                            status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(text))
        errors, valid = [], []
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            ser = self.get_serializer(data={k: v for k, v in row.items() if v != ""})
            if ser.is_valid():
                valid.append(ser)
            else:
                errors.append({"row": i, "errors": ser.errors})

        result = {"rows": len(valid) + len(errors), "valid": len(valid),
                  "errors": errors, "dry_run": dry_run, "created": 0}
        if errors or dry_run:
            return Response(result)
        with transaction.atomic():
            for ser in valid:
                self.perform_create(ser)
        result["created"] = len(valid)
        return Response(result, status=status.HTTP_201_CREATED)


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, ensure_ascii=False)
    return value

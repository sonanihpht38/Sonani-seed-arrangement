# ============================= API LAYER =============================
# Thin view: validate -> service -> respond. All rules live in services.py.
# The Import action is gated on the seed_import form's "save" permission; the
# audit user (EntryBy) is taken from the JWT.

import io
import os
import traceback
import zipfile

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.access.permissions import HasFormPermission
from modules.core.exceptions import ConflictError

from . import engine_runner
from .jobs import create_job, get_job, job_to_json
from .models import DomainError, SeedPlate
from .serializers import BatchSerializer, SeedImportRequestSerializer, SeedPlateSerializer
from .services import (
    ArrangementService, BatchService, InventoryService, PlateService, SeedImportService,
)

# CRUD action -> required form action on the 'plate_master' form.
_PLATE_PERM = {
    "list": "view", "retrieve": "view",
    "create": "create", "update": "edit", "partial_update": "edit", "destroy": "delete",
    # Unassigning changes the plate's state, not the inventory — same right as
    # an edit, so a user who may correct a plate may also free it.
    "release": "edit",
}

_VALID_ACTIONS = {"arrange", "machinefill", "compare", "enhanced"}
_REQUIRED_NUM = ["plateD", "margin", "tLo", "tHi", "minSeed", "squareTol", "clearance", "grid"]


def _not_number(v):
    try:
        float(v)
        return False
    except (TypeError, ValueError):
        return True


class JobsView(APIView):
    """POST an arrange / machinefill / compare job over the seeds in TRN_SeedData.
    Returns {id}; poll JobDetailView until status is done/failed."""

    permission_classes = [HasFormPermission.require("result_generation", "save")]

    def post(self, request):
        action = request.data.get("action")
        params = dict(request.data.get("params") or {})
        if action not in _VALID_ACTIONS:
            return Response({"detail": f"invalid action: {action}"}, status=status.HTTP_400_BAD_REQUEST)
        bad = [k for k in _REQUIRED_NUM if _not_number(params.get(k))]
        if bad:
            return Response({"detail": "missing or invalid values: " + ", ".join(bad)}, status=status.HTTP_400_BAD_REQUEST)
        raw = params.get("batches") or []
        if isinstance(raw, str):
            raw = [raw]
        params["batches"] = sorted(str(b).strip() for b in raw if str(b).strip())
        job_id = create_job(action, params)
        return Response({"id": job_id}, status=status.HTTP_201_CREATED)


class JobDetailView(APIView):
    """Poll a job's status / progress / result."""

    permission_classes = [HasFormPermission.require("result_generation", "view")]

    def get(self, request, job_id):
        j = get_job(job_id)
        if not j:
            return Response({"detail": "job not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(job_to_json(j))


class GenerateFinalView(APIView):
    """Regenerate the FINALIZED plate images for a job's arrangement (Form 6)."""

    permission_classes = [HasFormPermission.require("finalization", "save")]

    def post(self, request, job_id):
        j = get_job(job_id)
        if not j:
            return Response({"detail": "job not found"}, status=status.HTTP_404_NOT_FOUND)
        arrange_id = (j.get("result") or {}).get("arrangeId")
        if not arrange_id:
            return Response({"detail": "this job has no saved arrangement"}, status=status.HTTP_400_BAD_REQUEST)
        out_dir = os.path.join(settings.MEDIA_ROOT, "jobs", job_id)
        media_base = f"{settings.MEDIA_URL.rstrip('/')}/jobs/{job_id}"
        try:
            plates = engine_runner.generate_final(dict(j["params"]), arrange_id, out_dir, media_base)
        except Exception as exc:  # noqa: BLE001 - surface generation errors
            payload = {"detail": str(exc)}
            if settings.DEBUG:
                payload["trace"] = traceback.format_exc()
            return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"plates": plates})


class ArrangementListView(APIView):
    """Every arrangement run, newest first — the Arrangement History screen."""

    permission_classes = [HasFormPermission.require("arrangement_history", "view")]

    def get(self, request):
        return Response(ArrangementService.list())


class ArrangementDetailView(APIView):
    """One arrangement run: header + one row per plate."""

    permission_classes = [HasFormPermission.require("arrangement_history", "view")]

    def get(self, request, arrange_id):
        try:
            return Response(ArrangementService.detail(arrange_id))
        except DomainError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)


class PlateNamesView(APIView):
    """Current plate-name assignments for an arrangement (plateNo → name)."""

    permission_classes = [HasFormPermission.require("finalization", "view")]

    def get(self, request, arrange_id):
        return Response({"names": PlateService.names(arrange_id)})


class AssignPlateView(APIView):
    """Assign a plate name to a plate. Body {arrangeId, plateNo, plateName}."""

    permission_classes = [HasFormPermission.require("finalization", "save")]

    def post(self, request):
        try:
            res = PlateService.assign(
                request.data.get("arrangeId"), request.data.get("plateNo"),
                request.data.get("plateName"), getattr(request.user, "id", None),
            )
        except ConflictError:
            raise          # 409 via the global handler — a seed clash is not a 400
        except DomainError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(res)


class ReleasePlateView(APIView):
    """Release a plate name back to the pool. Body {arrangeId, plateNo}."""

    permission_classes = [HasFormPermission.require("finalization", "save")]

    def post(self, request):
        return Response(PlateService.release(
            request.data.get("arrangeId"), request.data.get("plateNo"),
            getattr(request.user, "id", None)))


class FinalizeArrangementView(APIView):
    """Inventory state of one arrangement.

    Seeds are consumed per PLATE, when that plate is assigned a name — see
    PlateService.assign — so there is no "finalize the run" action here.

    GET    → status: which plates are committed, how much inventory is left.
    DELETE → recovery: return EVERY seed this run is holding, whichever plate
             took it. The way back from a bulk consume.
    """

    def get_permissions(self):
        act = "view" if self.request.method == "GET" else "save"
        return [HasFormPermission.require("finalization", act)()]

    def get(self, request, arrange_id):
        return Response(InventoryService.status(arrange_id))

    def delete(self, request, arrange_id):
        return Response(InventoryService.unfinalize(
            arrange_id, getattr(request.user, "id", None)))


class PlateMasterViewSet(viewsets.ModelViewSet):
    """CRUD for the MST_SeedPlate plate-name inventory master (Plate Master form)."""

    serializer_class = SeedPlateSerializer
    queryset = SeedPlate.objects.all().order_by("plate_name", "plate_id")
    pagination_class = None

    def get_permissions(self):
        return [HasFormPermission.require("plate_master", _PLATE_PERM.get(self.action, "view"))()]

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        """Free this plate back to the pool — the Plate Master "Unassign" action.

        Finalization's /production/plates/release needs (arrangeId, plateNo);
        this screen has neither, so it gets its own door onto the same rule.
        """
        return Response(PlateService.release_plate(pk))

    def perform_destroy(self, instance):
        """Refuse to delete a plate an arrangement is still using.

        The delete used to go through and take the master row with it, leaving
        TRN_SeedPlate naming a Plate_ID that no longer existed — the arrangement
        still claimed the plate, but nothing recorded that it was taken, so the
        same physical plate could be handed to a second arrangement. Blocking is
        the safe half of that trade: the plate can still be removed, it just has
        to be unassigned first, which is now possible from this very screen.
        """
        if instance.is_used and not instance.is_released:
            raise ConflictError(
                f"Plate \"{instance.plate_name}\" is assigned to an arrangement. "
                f"Unassign it first, then delete."
            )
        instance.delete()


class AvailablePlatesView(APIView):
    """Plate names AVAILABLE to assign in Finalization — from MST_SeedPlate: not
    currently in use (ISUsed unset/0) OR released (IsReleased=1). ?all=1 lists every
    active plate with its status."""

    permission_classes = [HasFormPermission.require("finalization", "view")]

    def get(self, request):
        qs = SeedPlate.objects.filter(is_active=True).exclude(plate_name__isnull=True)
        if request.query_params.get("all") not in ("1", "true", "yes"):
            qs = qs.filter(Q(is_used__isnull=True) | Q(is_used=False) | Q(is_released=True))
        rows = [
            {
                "plateId": p.plate_id, "plateName": p.plate_name,
                "diameter": float(p.diameter) if p.diameter is not None else None,
                "isUsed": bool(p.is_used), "isReleased": bool(p.is_released),
            }
            for p in qs.order_by("plate_name", "plate_id")
        ]
        return Response(rows)


class FinalizedPlatesView(APIView):
    """Every plate that has been finalized (i.e. carries an assigned name).

    Read from TRN_SeedPlate, so the list is there whether or not the run that
    produced a plate is still open — the Finalization screen's per-plate view
    needs a live job, this does not.
    """

    permission_classes = [HasFormPermission.require("finalization", "view")]

    def get(self, request):
        return Response(PlateService.finalized_list())


class DownloadPlatesView(APIView):
    """Zip the selected plates' artifacts (Form 7). Body {plateNos:[...], include:
    "data"|"images"|"both"} → a .zip streamed back. Data = per-plate Excel (Compare);
    images = the Arrange / Machine-Cut / Finalized PNGs that exist for each plate."""

    permission_classes = [HasFormPermission.require("download", "view")]
    _IMG_SUBDIRS = ("arrange", "machinefill", "enhanced", "final")

    def post(self, request, job_id):
        j = get_job(job_id)
        if not j:
            return Response({"detail": "job not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            plate_nos = [int(n) for n in (request.data.get("plateNos") or [])]
        except (TypeError, ValueError):
            return Response({"detail": "invalid plateNos"}, status=status.HTTP_400_BAD_REQUEST)
        if not plate_nos:
            return Response({"detail": "select at least one plate"}, status=status.HTTP_400_BAD_REQUEST)
        include = request.data.get("include", "both")

        job_dir = os.path.join(settings.MEDIA_ROOT, "jobs", job_id)
        buf = io.BytesIO()
        added = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in plate_nos:
                nn = f"{n:02d}"
                if include in ("data", "both"):
                    p = os.path.join(job_dir, "excel", f"plate_{nn}.xlsx")
                    if os.path.exists(p):
                        z.write(p, f"plate_{nn}/plate_{nn}.xlsx")
                        added += 1
                if include in ("images", "both"):
                    for sub in self._IMG_SUBDIRS:
                        p = os.path.join(job_dir, sub, f"plate_{nn}.png")
                        if os.path.exists(p):
                            z.write(p, f"plate_{nn}/{sub}_plate_{nn}.png")
                            added += 1
        if added == 0:
            return Response({"detail": "no files found for the selected plates"}, status=status.HTTP_404_NOT_FOUND)
        resp = HttpResponse(buf.getvalue(), content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="plates_{job_id}.zip"'
        return resp


class BatchListView(APIView):
    """GET the batches (with seed counts) for the Batch Selection screen."""

    permission_classes = [HasFormPermission.require("batch_selection", "view")]

    def get(self, request):
        batches = BatchService.list_with_counts()
        return Response(BatchSerializer(batches, many=True).data)


class SeedImportView(APIView):
    """POST a seed datasheet (.xlsx) → parse, auto-create batches, skip duplicate
    stock numbers, insert the new rows into TRN_SeedData."""

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [HasFormPermission.require("seed_import", "save")]

    def post(self, request):
        s = SeedImportRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = SeedImportService.import_seeds(
                s.validated_data["file"], entry_by=request.user.id,
            )
        except DomainError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)

"""
Liveness vs readiness — two different questions a load balancer / orchestrator asks.

  /health  (liveness):  "is the process up?"  Cheap, no dependencies. If this
            fails, the orchestrator restarts the container. It must NOT touch the
            DB, or a slow DB would trigger pointless restart storms.

  /ready   (readiness): "can this instance serve traffic right now?"  Checks the
            DB and cache. If it returns 503, the load balancer drains this
            instance but does NOT kill it — e.g. during a brief DB blip or right
            after boot before migrations finish.
"""

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def liveness(_request):
    return JsonResponse({"status": "ok"})


def readiness(_request):
    checks = {}
    healthy = True

    # Database round-trip.
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure, don't crash the probe
        checks["database"] = f"error: {exc}"
        healthy = False

    # Cache round-trip.
    try:
        cache.set("readiness:probe", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("readiness:probe") == "1" else "error: readback mismatch"
        healthy = healthy and checks["cache"] == "ok"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"
        healthy = False

    return JsonResponse(
        {"status": "ready" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
    )

"""Celery tasks for the production module.

The arrangement engine (matplotlib + shapely, several seconds of CPU) runs here
rather than on the request path, which is what lets the api tier stay stateless
and thread-bound. Progress is written to the shared cache as the engine reports
it, so any api replica can serve the poll.

Artifacts (plate PNGs, per-plate Excel) are written under MEDIA_ROOT. With more
than one replica that directory must be shared storage (a volume, or blob
storage fronted by nginx) — the worker writes them, the web tier serves them.
"""

import os
import traceback

from celery import shared_task
from django.conf import settings

from . import engine_runner
from .jobs import get_job, update_job


@shared_task(
    name="production.run_arrangement_job",
    # The engine is CPU-bound and not idempotent (it writes an arrangement row),
    # so a lost worker must NOT silently re-run it behind the user's back.
    acks_late=False,
    ignore_result=True,
)
def run_arrangement_job(job_id):
    """Run one arrange / machinefill / compare / enhanced job to completion."""
    job = get_job(job_id)
    if job is None:  # cache evicted, or the job expired before a worker took it
        return

    update_job(job_id, status="running", progress=5)

    out_dir = os.path.join(settings.MEDIA_ROOT, "jobs", job_id)
    os.makedirs(out_dir, exist_ok=True)
    media_base = f"{settings.MEDIA_URL.rstrip('/')}/jobs/{job_id}"

    def progress(pct):
        update_job(job_id, progress=max(5, min(99, int(pct))))

    try:
        result = engine_runner.run(
            action=job["action"], params=dict(job["params"]),
            out_dir=out_dir, media_base=media_base, progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 - top-level job guard; surface to the UI
        update_job(job_id, status="failed", error=f"{exc}\n{traceback.format_exc()}")
        raise
    update_job(job_id, result=result, status="done", progress=100)

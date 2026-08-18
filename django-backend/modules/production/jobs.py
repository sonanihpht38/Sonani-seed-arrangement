"""Job store for the arrangement engine — shared, not per-process.

The packing engine is CPU-bound for several seconds, so a job is dispatched to
Celery (see `tasks.py`) and the POST returns immediately with status "queued";
the frontend polls GET /production/jobs/<id> until "done".

Job state lives in the Django cache (Redis in production, per-process locmem in
development), NOT in a module-level dict. That is what makes polling correct
behind the load balancer: the worker that runs the job and the api replica that
answers the poll are different processes, and both reach the same Redis.

`JOB_TTL` bounds how long a finished job stays pollable. The plate artifacts it
wrote under MEDIA_ROOT outlive it — they are addressed by URL, not by job state.
"""

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

# Long enough for a user to finish the Result → Finalize → Download flow.
JOB_TTL = 24 * 3600

_KEY = "production:job:{}"

_LOCMEM = "django.core.cache.backends.locmem.LocMemCache"


def _assert_shared_cache():
    """The web process writes the job row; a Celery worker reads it. A per-process
    cache makes that invisible across the process boundary, so the job would sit
    at "queued" forever. Fail with an actionable message instead of hanging."""
    if settings.CACHES["default"]["BACKEND"] != _LOCMEM:
        return
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return  # single process, runs inline — locmem is fine
    raise ImproperlyConfigured(
        "Arrangement jobs need a cache shared between the web process and the "
        "Celery worker, but CACHES['default'] is LocMemCache (per-process). "
        "Set REDIS_URL and run a worker (celery -A config worker -l info), or "
        "set CELERY_TASK_ALWAYS_EAGER=True to run jobs inline."
    )


def _key(job_id):
    return _KEY.format(job_id)


def new_job_id():
    """A job id. uuid4 (not a counter) so ids don't collide across replicas."""
    import uuid

    return "job-" + uuid.uuid4().hex[:12]


def save_job(job):
    cache.set(_key(job["id"]), job, JOB_TTL)


def create_job(action, params):
    """Register a queued job and hand it to Celery. Returns the job id.

    The row is written to the cache BEFORE the task is queued, so a worker that
    picks the job up instantly still finds it.
    """
    from .tasks import run_arrangement_job

    _assert_shared_cache()
    job_id = new_job_id()
    save_job({
        "id": job_id, "action": action, "params": dict(params),
        "status": "queued", "progress": 0, "result": None, "error": None,
    })
    run_arrangement_job.delay(job_id)
    return job_id


def get_job(job_id):
    return cache.get(_key(job_id))


def update_job(job_id, **kw):
    """Read-modify-write one job row.

    Not atomic: a lost update here can only mean a skipped progress tick, since
    exactly one worker owns a job and the api replicas never write. Status and
    result are written by that single owner.
    """
    job = cache.get(_key(job_id))
    if job is None:
        return None
    job.update(kw)
    cache.set(_key(job_id), job, JOB_TTL)
    return job


def job_to_json(j):
    """Shape the job for the frontend (same contract as the SEED app)."""
    result = j.get("result") or {}
    return {
        "id": j["id"],
        "action": j["action"],
        "status": j["status"],
        "progress": j["progress"],
        "error": j.get("error"),
        "plates": result.get("plates", []),
        "pairs": result.get("pairs", []),
        "arrangeAvg": result.get("arrangeAvg", 0),
        "machineAvg": result.get("machineAvg", 0),
        "enhancedAvg": result.get("enhancedAvg", 0),
        "arrangeId": result.get("arrangeId"),
        "seedsMatched": result.get("seedsMatched"),
    }

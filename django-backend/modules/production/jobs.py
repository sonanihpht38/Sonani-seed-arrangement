"""Job store for the arrangement engine — shared, not per-process.

The packing engine is CPU-bound for several seconds, so a job is dispatched to
Celery (see `tasks.py`) and the POST returns immediately with status "queued";
the frontend polls GET /production/jobs/<id> until "done".

Job state lives in the `jobs` cache alias — by default a table in the project's
own database — NOT in a module-level dict and NOT in the general-purpose cache.
That is what makes polling correct behind the load balancer: the worker that runs
the job and the api replica that answers the poll are different processes, and
both read the same row. It also survives a restart, which a memory-backed store
does not: an app-pool recycle used to take every in-flight job with it.

`JOB_TTL` bounds how long a finished job stays pollable. The plate artifacts it
wrote under MEDIA_ROOT outlive it — they are addressed by URL, not by job state.
"""

from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured

# Long enough for a user to finish the Result → Finalize → Download flow.
JOB_TTL = 24 * 3600

_KEY = "production:job:{}"

_LOCMEM = "django.core.cache.backends.locmem.LocMemCache"


def _store():
    """The job store — its OWN cache alias, not the general-purpose one.

    See the JOB_CACHE_URL block in settings for why jobs may not share the
    default cache: that one is either per-process or configured to swallow its
    own failures, and both turn a live job into "job not found" on the next poll.
    """
    return caches["jobs"]


def _assert_shared_cache():
    """The web process writes the job row; a Celery worker reads it. A per-process
    cache makes that invisible across the process boundary, so the job would sit
    at "queued" forever. Fail with an actionable message instead of hanging."""
    if settings.CACHES["jobs"]["BACKEND"] != _LOCMEM:
        return
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return  # single process, runs inline — locmem is fine
    raise ImproperlyConfigured(
        "Arrangement jobs need a store shared between the web process and the "
        "Celery worker, but CACHES['jobs'] is LocMemCache (per-process). "
        "Leave JOB_CACHE_URL unset to use the database store (run "
        "`python manage.py createcachetable` once), or point it at Redis."
    )


def _key(job_id):
    return _KEY.format(job_id)


def new_job_id():
    """A job id. uuid4 (not a counter) so ids don't collide across replicas."""
    import uuid

    return "job-" + uuid.uuid4().hex[:12]


def save_job(job):
    _store().set(_key(job["id"]), job, JOB_TTL)


def create_job(action, params):
    """Register a queued job and hand it to Celery. Returns the job id.

    The row is written to the store BEFORE the task is queued, so a worker that
    picks the job up instantly still finds it.
    """
    from .tasks import run_arrangement_job

    _assert_shared_cache()
    job_id = new_job_id()
    save_job({
        "id": job_id, "action": action, "params": dict(params),
        "status": "queued", "progress": 0, "result": None, "error": None,
    })
    # READ IT BACK before promising the caller an id.
    #
    # A store that drops writes does so silently — a Redis cache configured with
    # IGNORE_EXCEPTIONS returns None on both set and get, and a per-process cache
    # answers only in the process that wrote. Either way the POST used to hand
    # back an id that every later poll answered "job not found" for, with the
    # progress bar frozen on screen and nothing in the log. One extra read turns
    # that into an error at the moment the job is created, naming the cause.
    if get_job(job_id) is None:
        raise ImproperlyConfigured(
            "The arrangement job store is not holding jobs: %s accepted a write "
            "and returned nothing when read straight back. Jobs cannot be polled "
            "in this state. Check CACHES['jobs'] — with the database store, run "
            "`python manage.py createcachetable`."
            % settings.CACHES["jobs"]["BACKEND"]
        )
    run_arrangement_job.delay(job_id)
    return job_id


def get_job(job_id):
    return _store().get(_key(job_id))


def update_job(job_id, **kw):
    """Read-modify-write one job row.

    Not atomic: a lost update here can only mean a skipped progress tick, since
    exactly one worker owns a job and the api replicas never write. Status and
    result are written by that single owner.
    """
    job = _store().get(_key(job_id))
    if job is None:
        return None
    job.update(kw)
    _store().set(_key(job_id), job, JOB_TTL)
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

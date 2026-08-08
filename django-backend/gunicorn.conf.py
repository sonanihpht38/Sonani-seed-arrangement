"""
Gunicorn configuration.

Worker class choice — important for this stack:
  The database driver is pyodbc (via mssql-django), a blocking C extension. gevent
  monkey-patching does NOT make pyodbc cooperative, so async workers would block
  the whole event loop on every query. `gthread` (threads) is the right model:
  while one thread waits on SQL Server I/O, others serve requests. This gives
  real concurrency for an I/O-bound ORM app without fighting the driver.

Sizing (override via env):
  WEB_CONCURRENCY (processes) ~= 2 * CPU cores. THREADS per worker handles the
  I/O-wait concurrency. Total in-flight requests per container ≈ workers * threads.
  Remember: total DB connections across the fleet ≈ containers * workers * threads
  * CONN_MAX_AGE-reuse — keep it under SQL Server's healthy connection budget.

max_requests recycles workers periodically to bound memory growth / leaks.
"""

import multiprocessing
import os


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

workers = _int("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1)
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
threads = _int("GUNICORN_THREADS", 4)
worker_connections = _int("GUNICORN_WORKER_CONNECTIONS", 1000)

# Recycle workers to cap memory creep; jitter avoids all workers recycling at once.
max_requests = _int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _int("GUNICORN_MAX_REQUESTS_JITTER", 100)

timeout = _int("GUNICORN_TIMEOUT", 30)
graceful_timeout = _int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _int("GUNICORN_KEEPALIVE", 5)

# Log to stdout/stderr so the container runtime collects them.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
# Include the request id we set on the response so access logs correlate with app logs.
access_log_format = '%(h)s %(l)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(D)sµs rid=%({x-request-id}o)s'

# Load the app before forking workers: shares read-only memory (copy-on-write)
# and surfaces import/boot errors once instead of per worker.
preload_app = os.environ.get("GUNICORN_PRELOAD", "true").lower() == "true"

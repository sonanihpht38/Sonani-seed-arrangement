"""
Base settings — shared by every environment and driven entirely by env vars.

Design goals for a system aiming at high concurrency:
  * Stateless app tier (JWT auth, cache-backed sessions) -> scales horizontally.
  * Connection reuse to the database (CONN_MAX_AGE) so we don't pay a TCP + TLS +
    auth handshake to SQL Server on every request.
  * A shared Redis cache used for read caching, DRF throttle counters, and
    sessions — the one piece of shared state all app replicas agree on.
  * Every list endpoint is paginated and every client is throttled by default,
    so a single caller can never ask the DB for "everything".
  * Structured JSON logs with a per-request id, so a request can be traced across
    the load balancer -> app -> worker.

Per-environment files (`development.py`, `production.py`) import everything from
here and override the few things that legitimately differ (DEBUG, security
headers, allowed hosts, error reporting).
"""

from datetime import timedelta
from pathlib import Path

import environ

# config/settings/base.py -> parents[2] == django-backend project root.
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
# Read a local .env if present (never committed). In containers, real env vars win.
environ.Env.read_env(BASE_DIR / ".env")

# ---- Core -------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---- Applications -----------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
    "django_prometheus",  # /metrics for scraping request latency + counts
    "drf_spectacular",    # OpenAPI schema at /api/schema -> frontend type codegen
]

# Each business module is a self-contained app. New module = new line here.
LOCAL_APPS = [
    "modules.core",       # shared ERP framework: tenant bases, pagination, catalogue
    "modules.accounts",   # identity, roles, login (/me)
    "modules.masters",    # company (tenant root) + system settings + lookup master data
    "modules.access",     # form-permission RBAC (roles -> forms, CRUD flags)
    "modules.notifications",  # per-user notifications (top-bar bell)
    "modules.production",  # diamond plate-arrangement workflow (seed import -> download)
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Middleware order matters. Prometheus brackets the stack to time the whole
# request; WhiteNoise serves static right after security; the request-id
# middleware runs early so every downstream log line carries the id.
MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "config.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "modules.core.tenancy.TenantContextMiddleware",  # session-auth tenant scope; JWT is set per-view
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---- Database ---------------------------------------------------------------
# DB_ENGINE=mssql  -> SQL Server via mssql-django (production).
# DB_ENGINE=sqlite -> zero-setup local dev (default).
#
# CONN_MAX_AGE keeps a physical connection alive and reused across requests
# instead of reconnecting each time. Keep it modest: total connections held is
# roughly (app_instances * gunicorn_workers * threads) and must stay well under
# SQL Server's healthy connection budget.
DB_ENGINE = env("DB_ENGINE", default="sqlite")
DB_CONN_MAX_AGE = env.int("DB_CONN_MAX_AGE", default=60)

if DB_ENGINE == "mssql":
    DATABASES = {
        "default": {
            "ENGINE": "mssql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST"),
            "PORT": env("DB_PORT", default="1433"),
            "OPTIONS": {
                "driver": env("DB_ODBC_DRIVER", default="ODBC Driver 18 for SQL Server"),
                # Encrypt in transit; TrustServerCertificate=yes is fine for a
                # private network / self-signed dev cert. Set to "no" with a real
                # CA-signed cert in production.
                "extra_params": env(
                    "DB_EXTRA_PARAMS",
                    default="Encrypt=yes;TrustServerCertificate=yes",
                ),
            },
            "CONN_MAX_AGE": DB_CONN_MAX_AGE,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": env.db(
            "DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
        ),
    }
    DATABASES["default"]["CONN_MAX_AGE"] = DB_CONN_MAX_AGE
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# ---- Cache & sessions (Redis) ----------------------------------------------
# One Redis serves three jobs: response/read caching, DRF throttle counters, and
# sessions. All app replicas share it, which is what makes throttling and
# sessions correct when you run more than one instance. Without REDIS_URL we fall
# back to a per-process in-memory cache so local dev needs no Redis.
REDIS_URL = env("REDIS_URL", default="")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,  # cache down != site down
            },
            "KEY_PREFIX": env("CACHE_KEY_PREFIX", default="sonani"),
        }
    }
    # Sessions in the cache -> no per-request DB write, and any replica can read
    # any session. Requires JWT for the API anyway, so this is only for admin.
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"
else:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    }

# ---- Auth -------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- DRF --------------------------------------------------------------------
# Pagination and throttling are ON by default. Throttle counters live in the
# Redis cache above, so limits are shared across every app replica instead of
# being per-process (the classic mistake that lets N replicas grant N x the
# limit). Renderers: the browsable API is dev-only (see development.py); prod
# returns pure JSON.
REST_FRAMEWORK = {
    # JWT only. The React client authenticates with a Bearer token; it never uses
    # cookies. SessionAuthentication was also enabled, which meant that once a user
    # signed into the Django admin (same browser, same origin), its CSRF check
    # fired on every cookie-carrying API POST that had no Bearer token — Register,
    # Login, Forgot/Reset password — failing with "CSRF Failed: CSRF token
    # missing." The admin has its own session auth and is unaffected by this.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": env.int("DRF_PAGE_SIZE", default=25),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "user": env("THROTTLE_USER", default="1000/hour"),
        "anon": env("THROTTLE_ANON", default="60/hour"),
        # Attach `throttle_scope = "login"` to the token view to brute-force-guard it.
        "login": env("THROTTLE_LOGIN", default="10/min"),
    },
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    # DomainError raised anywhere (service/model/view) renders as {"detail": ...}
    # with the error's http_status — no per-view try/except.
    "EXCEPTION_HANDLER": "modules.core.exceptions.domain_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sonani Seed Arrangement API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Legacy hand-rolled viewsets produce a rough schema; every TenantCrudViewSet
    # module is serializer-driven and comes out accurate. Silence the noise.
    "DISABLE_ERRORS_AND_WARNINGS": True,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("ACCESS_TOKEN_LIFETIME_MIN", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", default=7)),
}

# ---- CORS / CSRF ------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173"])

# ---- Celery (async task queue) ---------------------------------------------
# Anything slow or I/O-bound that must not block the HTTP response goes here:
# email/OTP, report + export generation, cache warming. Broker + result backend
# default to Redis. See config/celery.py.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL or "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL or "redis://localhost:6379/2")
CELERY_TASK_ACKS_LATE = True                 # redeliver if a worker dies mid-task
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# Dev escape hatch: run tasks inline, in-process, with no broker or worker.
# modules.production's arrangement jobs also accept this instead of Redis.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_WORKER_PREFETCH_MULTIPLIER = env.int("CELERY_PREFETCH", default=1)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=300)
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=270)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Beat schedule. Run the scheduler with `celery -A config beat -l info`
# alongside a worker. No periodic tasks are registered right now — arrangement
# jobs are dispatched on demand, not on a schedule.
CELERY_BEAT_SCHEDULE = {}

# ---- Email (SMTP) -----------------------------------------------------------
# Set EMAIL_HOST (+ creds) in the environment to send real mail via SMTP; with no
# host configured we fall back to the console backend so local dev prints the
# email (including the password-reset link) to the server log — no SMTP needed.
EMAIL_HOST = env("EMAIL_HOST", default="")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
    EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
    EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Sonani Seed Arrangement <no-reply@sonani.local>")
# Where the SPA is served — used to build the password-reset link in the email.
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")
# Password-reset token lifetime (seconds). Django's default is 3 days; tighten it.
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=1800)

# ---- i18n / static ----------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

CELERY_TIMEZONE = TIME_ZONE

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# WhiteNoise: hashed, compressed static files served straight from the app with
# far-future cache headers — no separate static server needed for admin/DRF assets.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---- Media (production module job artifacts) ---------------------------------
# Local disk by default; point STORAGES["default"] at S3/Azure Blob in prod.
#
# MEDIA_ROOT holds the production module's job artifacts (plate PNGs and
# per-plate Excel under media/jobs/<job-id>/). The Celery worker WRITES them and
# the web tier SERVES them, so with more than one replica this must be shared
# storage — a mounted volume, or blob storage fronted by nginx.
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# Let the app serve MEDIA_ROOT itself. Off here; development.py defaults it to
# DEBUG. Set it explicitly when running a dev stack with DEBUG=false (e.g. bound
# to a LAN IP) — otherwise plate images 404. Never enable it in a real
# deployment: nginx serves /media there (see react-frontend/nginx.conf).
SERVE_MEDIA = env.bool("SERVE_MEDIA", default=False)

# Seed datasheets exceed Django's 2.5 MB default request-body limit.
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024

# Integer IDENTITY primary keys (int, not bigint) across all models.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# ---- Logging (structured JSON to stdout) ------------------------------------
# Containers log to stdout; a collector (Loki/ELK/CloudWatch/Azure Monitor)
# ships them. JSON + a request_id field makes them queryable and lets you follow
# one request end to end. LOG_JSON=false gives human-readable console logs in dev.
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOG_JSON = env.bool("LOG_JSON", default=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.middleware.RequestIDLogFilter"},
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
        },
        "console": {
            "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "json" if LOG_JSON else "console",
        },
    },
    "root": {"handlers": ["stdout"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"handlers": ["stdout"], "level": "ERROR", "propagate": False},
        "gunicorn.error": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
    },
}

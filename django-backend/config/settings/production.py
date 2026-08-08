"""
Production overrides — security hardening + error reporting.

Everything here is the delta from base for a real deployment behind a TLS-
terminating load balancer/reverse proxy. The app never sees plain HTTP in
production; the proxy sets X-Forwarded-Proto, which SECURE_PROXY_SSL_HEADER
teaches Django to trust.
"""

import sys

from .base import BASE_DIR, env  # noqa: F401
from .base import *  # noqa: F401,F403

DEBUG = False

# ALLOWED_HOSTS / CSRF / CORS are required in prod — fail loud if unset rather
# than silently accepting requests for any host.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")

# Refuse to boot with the throwaway dev secret.
SECRET_KEY = env("SECRET_KEY")
if SECRET_KEY == "dev-insecure-change-me" and "collectstatic" not in sys.argv:
    raise RuntimeError("SECRET_KEY must be set to a strong, unique value in production.")

# ---- HTTPS / transport security --------------------------------------------
# The load balancer terminates TLS and forwards this header on the secure hop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# ---- Error reporting (Sentry, optional) -------------------------------------
# Set SENTRY_DSN to turn on exception + performance capture. No-op if unset, so
# the same image runs with or without it.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
        send_default_pii=False,
        environment=env("DJANGO_ENV", default="production"),
        release=env("RELEASE_VERSION", default=""),
    )

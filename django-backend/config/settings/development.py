"""
Development overrides.

Optimised for a fast local loop: DEBUG on, the DRF browsable API back, and
human-readable logs. Defaults to sqlite + the in-memory cache so `runserver`
works with zero external services. Point DB_ENGINE/REDIS_URL at the compose
stack when you want to exercise the real thing.
"""

from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK, env

# Defaults on, but honour DEBUG from the environment: when this dev stack is
# reachable from the network (e.g. bound to a LAN IP), DEBUG=false stops the
# traceback page from exposing SECRET_KEY and DB_PASSWORD to anyone who can
# trigger a 500.
DEBUG = env.bool("DEBUG", default=True)

# The app serves plate images itself in dev. Follows DEBUG unless overridden, so
# a DEBUG=false dev stack still needs SERVE_MEDIA=true to render them.
SERVE_MEDIA = env.bool("SERVE_MEDIA", default=DEBUG)

# Show the browsable API in the browser during development only.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# Permissive by default, but honour ALLOWED_HOSTS from the environment so a dev
# stack exposed on a network can still validate the Host header.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

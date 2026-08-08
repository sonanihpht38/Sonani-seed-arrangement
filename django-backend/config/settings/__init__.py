# ============================================================================
# Settings selector.
#
# `DJANGO_SETTINGS_MODULE` stays `config.settings` everywhere (manage.py, wsgi,
# asgi, gunicorn) — this package picks the concrete environment module from the
# `DJANGO_ENV` variable so there is exactly one knob to flip between dev and prod.
#
#   DJANGO_ENV=development  ->  config/settings/development.py   (default)
#   DJANGO_ENV=production   ->  config/settings/production.py
# ============================================================================
import os

_ENV = os.environ.get("DJANGO_ENV", "development").lower()

if _ENV in ("production", "prod", "staging"):
    from .production import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403

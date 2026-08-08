#!/usr/bin/env sh
# ============================================================================
# Container entrypoint.
#
# Runs DB migrations, collects static files, then hands off (exec) to whatever
# CMD was given — gunicorn for the API, or `celery ...` for a worker/beat. Using
# `exec` means the real process becomes PID 1 so it receives SIGTERM directly
# and shuts down gracefully during rolling deploys.
#
# RUN_MIGRATIONS=false on worker/beat containers so only ONE container migrates.
# ============================================================================
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] Applying database migrations..."
  python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-true}" = "true" ]; then
  echo "[entrypoint] Collecting static files..."
  python manage.py collectstatic --noinput
fi

echo "[entrypoint] Starting: $*"
exec "$@"

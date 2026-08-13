@echo off
rem Django dev server for local work.
rem
rem CELERY_TASK_ALWAYS_EAGER=true runs arrangement jobs inline, so no Redis or
rem worker is needed - without it every plate job queues forever.
rem --noreload keeps ONE process, so the start time proves which code is live
rem (a stale auto-reload once made a fixed engine look unfixed).
cd /d "%~dp0.."
set DJANGO_ENV=development
set CELERY_TASK_ALWAYS_EAGER=true
set PYTHONUNBUFFERED=1
"django-backend\.venv\Scripts\python.exe" "django-backend\manage.py" runserver 127.0.0.1:8001 --noreload

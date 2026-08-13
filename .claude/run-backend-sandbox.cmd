@echo off
rem SANDBOX backend - port 8002, throwaway sqlite, NEVER the live SQL Server.
rem Used to exercise screens end to end without writing to production data.
rem The sqlite file is passed in as SANDBOX_DB by the caller.
cd /d "%~dp0.."
set DJANGO_ENV=development
set CELERY_TASK_ALWAYS_EAGER=true
set PYTHONUNBUFFERED=1
set DB_ENGINE=sqlite
set ALLOWED_HOSTS=localhost,127.0.0.1,testserver
if "%SANDBOX_DB%"=="" set "SANDBOX_DB=C:/Users/Hp/AppData/Local/Temp/claude/C--deep-kikani-sonani-seed-arrangement/4cf08da7-75fe-45b2-862c-5763a9af2da0/scratchpad/throwaway.sqlite3"
set DATABASE_URL=sqlite:///%SANDBOX_DB%
"django-backend\.venv\Scripts\python.exe" "django-backend\manage.py" runserver 127.0.0.1:8002 --noreload

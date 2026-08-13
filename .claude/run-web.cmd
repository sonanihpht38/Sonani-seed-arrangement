@echo off
rem Vite dev server for local work.
rem
rem node/npm are not on the spawner's PATH on this machine, so prepend them or
rem the launch fails with "spawn npm ENOENT".
rem Port 5174 is not a free choice: django-backend\.env lists exactly
rem localhost:5174 in CORS_ALLOWED_ORIGINS and CSRF_TRUSTED_ORIGINS, so any
rem other port gets the API calls rejected.
cd /d "%~dp0.."
set "PATH=C:\Program Files\nodejs;%PATH%"
set API_PROXY_TARGET=http://127.0.0.1:8001
npm --prefix react-frontend run dev -- --port 5174 --strictPort

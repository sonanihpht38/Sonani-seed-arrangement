@echo off
rem SANDBOX frontend - port 5175, proxying to the sandbox backend on 8002.
rem Same-origin through Vite's proxy, so the 5174-only CORS list does not apply.
cd /d "%~dp0.."
set "PATH=C:\Program Files\nodejs;%PATH%"
set API_PROXY_TARGET=http://127.0.0.1:8002
npm --prefix react-frontend run dev -- --port 5175 --strictPort

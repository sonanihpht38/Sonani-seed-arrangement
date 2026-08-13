@echo off
rem Serves the PRODUCTION build (dist/) exactly as a static server would, on
rem port 4173. Used to prove whether a white screen is the build's fault or the
rem deployment's — this serves the same bytes that get copied to live.
cd /d "%~dp0.."
set "PATH=C:\Program Files\nodejs;%PATH%"
npm --prefix react-frontend run preview -- --port 4173 --strictPort

# ============================================================================
# Sonani API (Django) — production image.
#
# Debian slim (not alpine): the Microsoft SQL Server ODBC driver (msodbcsql18)
# and pyodbc build cleanly against glibc; alpine/musl is a fight.
#
# Multi-stage: a builder compiles wheels, the runtime carries only what's needed.
# ============================================================================

# ---- Stage 1: build Python deps into wheels --------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Build toolchain + unixODBC headers so pyodbc compiles.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_ENV=production \
    DJANGO_SETTINGS_MODULE=config.settings

# Runtime OS deps + Microsoft ODBC Driver 18 for SQL Server.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg unixodbc \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install the pre-built wheels (no compiler in the runtime image).
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Non-root user.
RUN groupadd -r app && useradd -r -g app app
WORKDIR /app

COPY . .
RUN chmod +x entrypoint.sh && chown -R app:app /app
USER app

EXPOSE 8000

# Liveness probe hits the dependency-free /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').getcode()==200 else 1)" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]

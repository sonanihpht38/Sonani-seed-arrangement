# Sonani ERP — Production Architecture

This repo is a Django (DRF) + React (Vite) ERP wired for a **stateless, horizontally
scalable** deployment on SQL Server. This document explains *what* was set up and
*why*, plus how to take it from this single-host compose to real high concurrency.

---

## Runtime topology

```
                    ┌─────────────┐
   Browsers ───────▶│  CDN (opt.) │  static React bundle
                    └──────┬──────┘
                           │
                    ┌──────▼───────┐
                    │ Load Balancer│  (nginx / ALB / Azure App Gateway)
                    └──────┬───────┘
              ┌────────────┼────────────┐
        ┌─────▼─────┐ ┌────▼─────┐  ┌───▼──────┐
        │  web      │ │  api-1   │… │  api-N   │  gunicorn (gthread), stateless
        │ (nginx)   │ └────┬─────┘  └───┬──────┘
        └───────────┘      │            │
                    ┌──────▼────────────▼──────┐
                    │        Redis             │  cache + sessions + throttle + broker
                    └──────┬────────────┬──────┘
                           │            │
                    ┌──────▼─────┐  ┌───▼──────────┐
                    │ Celery     │  │ Celery beat  │  async jobs / schedules
                    │ worker(s)  │  └──────────────┘
                    └──────┬─────┘
                    ┌──────▼──────────────────────┐
                    │  SQL Server (managed)       │  primary (+ read replicas)
                    └─────────────────────────────┘
                     Observability: /metrics → Prometheus/Grafana, JSON logs, Sentry
```

The app tier holds **no local state** — auth is JWT, sessions/cache/throttle
counters live in Redis — so you scale by adding `api` replicas behind the LB.

---

## What was set up and why

### Configuration
- **Settings split** into `config/settings/{base,development,production}.py`, chosen
  by `DJANGO_ENV`. `DJANGO_SETTINGS_MODULE` stays `config.settings` everywhere.
- **12-factor env** via `django-environ` — one image, behavior driven by env vars.

### Database (SQL Server)
- `mssql-django` backend, all creds from env.
- **`CONN_MAX_AGE`** keeps physical connections alive/reused (no per-request
  reconnect); **`CONN_HEALTH_CHECKS`** discards dead ones.
- Connection-budget rule: `replicas × workers × threads` must stay under SQL
  Server's healthy connection count.

### Concurrency model
- **gunicorn `gthread` workers**, deliberately *not* gevent: the pyodbc driver is
  blocking C and won't cooperate with gevent monkey-patching. Threads give real
  concurrency while a request waits on SQL Server I/O. See `gunicorn.conf.py`.
- **Celery** for anything slow/I-O-bound off the request path (email/OTP, reports,
  exports, cache warming). Worker + beat are separate containers.

### Caching & sessions
- **Redis** via `django-redis`: response/read caching, cache-backed sessions,
  and shared DRF throttle counters. `IGNORE_EXCEPTIONS` so a Redis blip degrades
  gracefully instead of 500-ing.

### API hardening (DRF)
- **Pagination on by default** (`PAGE_SIZE`) — no endpoint can return "everything".
- **Throttling on by default** — `user`/`anon` global limits + a stricter `login`
  scope on the token endpoint (brute-force guard). Counters shared via Redis.
- Filter/search/ordering backends enabled; JSON-only renderer in production.

### Security (production.py)
- HTTPS: `SECURE_PROXY_SSL_HEADER`, SSL redirect, HSTS (1y, preload),
  secure+httponly cookies, nosniff, `X-Frame-Options: DENY`, referrer policy.
- Refuses to boot with the dev `SECRET_KEY` or missing `ALLOWED_HOSTS`.

### Observability
- **Structured JSON logs to stdout** with a **request id** stamped on every line
  and echoed as `X-Request-ID` (`config/middleware.py`) — trace one request across
  LB → app → worker.
- **Prometheus** `/metrics` (django-prometheus) for latency/throughput.
- **Sentry** auto-enabled when `SENTRY_DSN` is set (no-op otherwise).
- Probes: **`/health`** (liveness, dependency-free) and **`/ready`** (readiness,
  checks DB + cache, returns 503 to drain traffic).

### Production module (plate arrangement)
- Its 7 tables are **`managed = False`** — Django never creates them. The DDL in
  `modules/production/sql/` is the schema's source of truth; apply it with
  `manage.py init_production_schema` (idempotent, also back-fills added columns).
- Arrangement jobs are **Celery tasks**, not request-path work: the engine burns
  CPU for seconds in matplotlib/shapely. Job status lives in the **Redis cache**,
  not in process memory, so the worker that runs a job and the api replica that
  answers the poll can be different processes. Without a shared cache the module
  refuses to enqueue rather than hang (see `modules/production/jobs.py`).
- Job artifacts (plate PNGs, per-plate Excel) are written under
  `MEDIA_ROOT/jobs/<job-id>/` by the **worker** and served by the **web** tier —
  so beyond one replica `MEDIA_ROOT` must be shared storage, not container-local disk.

### Frontend
- **React Query** — client cache, request dedup, background refetch, smart retries;
  cuts redundant GET load with no API changes.
- **Code-splitting** per feature (`React.lazy` + `Suspense`) → small initial bundle.
- **Error boundary** so one screen's crash doesn't white-screen the app.
- Built by Vite (vendor chunk split), served by **nginx** with gzip, immutable
  caching of fingerprinted assets, no-cache `index.html`, and `/api` proxying.

### Delivery
- Multi-stage **Dockerfiles** (backend installs the MSSQL ODBC driver; both run
  as non-root with healthchecks), **docker-compose** for the whole stack,
  **GitHub Actions CI** (lint, checks, tests, builds), and a **Makefile**.

---

## Local usage

```bash
cp .env.example .env          # set a real SECRET_KEY + DB_PASSWORD
docker compose up --build     # db, redis, api, worker, beat, web
# Web:  http://localhost:8080     API:  http://localhost:8000
# Probes: /health /ready /metrics
docker compose --profile observability up   # + Prometheus (9090) & Grafana (3001)
```

Pure-backend dev without containers: `DJANGO_ENV=development` uses sqlite + an
in-memory cache, so `python manage.py runserver` needs no external services.
The production module is the exception — its tables are SQL Server DDL, and its
jobs need either Redis + a worker, or `CELERY_TASK_ALWAYS_EAGER=true` to run
inline.

---

## Going from here to 100k concurrent

This compose is single-host (parity/staging). For real scale:

1. **Managed data tier** — Azure SQL / SQL MI with **read replicas** (+ a DB router
   so GETs hit replicas); managed Redis (clustered). Drop the db/redis containers.
2. **Orchestrate** `api`/`worker` as many autoscaled replicas on **Kubernetes /
   Azure Container Apps / ECS** behind an LB; scale on p95 latency + CPU.
3. **PgBouncer-equivalent**: keep `replicas × workers × threads` bounded; front SQL
   Server with a connection concentrator if needed.
4. **CDN** for the React bundle (Azure Front Door / CloudFront) so app nodes serve
   only API traffic.
5. **Edge rate limiting / WAF** in front of DRF throttling.
6. **Dashboards + alerts** on the metrics/logs before you scale out, not after.
```

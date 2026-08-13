"""
Project URL configuration — the composition root for routing.

Each module owns its own urls.py; the host just includes them under /api/.
JWT token endpoints are provided here so the React client can obtain a Bearer
token. Adding a module = one more `path("api/...", include(...))` line.

Operational endpoints:
  /health   liveness probe (restart signal)
  /ready    readiness probe (traffic drain signal; checks DB + cache)
  /metrics  Prometheus scrape target (request latency, counts, etc.)
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from config.health import liveness, readiness

# The admin is the only place users, roles and permissions are managed (the
# Administration module was removed), so brand it like the rest of the product
# instead of leaving the stock "Django administration".
admin.site.site_header = "Sonani Seed Arrangement"
admin.site.site_title = "Sonani Seed Arrangement"
admin.site.index_title = "Administration"


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login endpoint with a dedicated, stricter throttle scope (brute-force guard)."""
    throttle_scope = "login"


urlpatterns = [
    path("admin/", admin.site.urls),

    # --- Operational probes / metrics ---
    path("health", liveness),
    path("ready", readiness),
    path("", include("django_prometheus.urls")),  # exposes /metrics

    # Auth: obtain / refresh a Bearer token, plus current-user endpoint.
    path("api/auth/token", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/", include("modules.accounts.urls")),

    # Feature modules — each owns its own routes.
    path("api/", include("modules.access.urls")),
    path("api/", include("modules.notifications.urls")),
    path("api/", include("modules.production.urls")),

    # OpenAPI: machine-readable schema + interactive docs. The frontend's
    # `npm run gen:api` consumes /api/schema/ to generate TS types.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

# Serve the production module's generated plate images / Excel from the app when
# SERVE_MEDIA is on (dev default). `django.conf.urls.static.static()` is a no-op
# once DEBUG is off, so wire the serve view directly — a DEBUG=false dev stack on
# a LAN IP still needs its images. Production fronts MEDIA_ROOT with nginx.
if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(
            rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]

# The SAME files, also reachable under /api/. Deployments that put a separate
# web server in front of the SPA proxy only /api to Django; a request for
# /media/... then never leaves that server, hits its SPA fallback and comes back
# as index.html with HTTP 200 and Content-Type text/html — so every plate image
# renders broken while the page itself works. Riding the /api prefix means the
# images follow the proxy rule that already exists, with no server config to add.
#
# Registered unconditionally, unlike the block above: it is the only route that
# works when nothing fronts MEDIA_ROOT.
urlpatterns += [
    re_path(
        rf"^api/{settings.MEDIA_URL.strip('/')}/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

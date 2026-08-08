# Form-permission / RBAC routes. Included by the project urls under /api/.
# Only the two read endpoints the app itself consumes are exposed: the sidebar
# catalogue and the current user's column visibility. Roles, permissions and the
# form catalogue are administered from the Django admin.
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CatalogueViewSet, visible_columns

router = DefaultRouter()
router.register(r"access/catalogue", CatalogueViewSet, basename="catalogue")

urlpatterns = router.urls + [
    path("access/visible-columns/", visible_columns),
]

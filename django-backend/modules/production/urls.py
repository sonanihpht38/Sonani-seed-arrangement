# Production module routes. Included by the project urls under /api/.
# Trailing slash matches the project convention (DRF router routes carry one).
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ArrangementDetailView, ArrangementListView, AssignPlateView, AvailablePlatesView, BatchListView,
    DownloadPlatesView, GenerateFinalView, JobDetailView, JobsView, PlateMasterViewSet, PlateNamesView,
    ReleasePlateView, SeedImportView,
)

router = DefaultRouter()
router.register(r"production/plate-master", PlateMasterViewSet, basename="plate-master")

urlpatterns = [
    path("production/seeds/import/", SeedImportView.as_view(), name="seed-import"),
    path("production/batches/", BatchListView.as_view(), name="batches"),
    path("production/jobs", JobsView.as_view(), name="jobs"),
    path("production/jobs/<str:job_id>", JobDetailView.as_view(), name="job-detail"),
    path("production/jobs/<str:job_id>/generate-final", GenerateFinalView.as_view(), name="generate-final"),
    path("production/plates", AvailablePlatesView.as_view(), name="available-plates"),
    path("production/plates/assign", AssignPlateView.as_view(), name="assign-plate"),
    path("production/plates/release", ReleasePlateView.as_view(), name="release-plate"),
    path("production/arrangements/", ArrangementListView.as_view(), name="arrangements"),
    path("production/arrangements/<str:arrange_id>/plate-names", PlateNamesView.as_view(), name="plate-names"),
    path("production/arrangements/<str:arrange_id>", ArrangementDetailView.as_view(), name="arrangement-detail"),
    path("production/jobs/<str:job_id>/download", DownloadPlatesView.as_view(), name="download-plates"),
] + router.urls

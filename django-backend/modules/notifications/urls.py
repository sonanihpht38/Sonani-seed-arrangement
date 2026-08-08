# Notification routes. Included by the project urls under /api/.
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notification")

urlpatterns = router.urls

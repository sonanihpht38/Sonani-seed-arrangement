# ============================= API LAYER =============================
# A user only ever sees their OWN notifications (scoped to request.user).

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _qs(self, request):
        return Notification.objects.filter(user=request.user)

    def list(self, request):
        # Most recent 50 for the dropdown.
        items = self._qs(request)[:50]
        return Response(NotificationSerializer(items, many=True).data)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"count": self._qs(request).filter(is_read=False).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = self._qs(request).filter(pk=pk).first()
        if n and not n.is_read:
            n.is_read = True
            n.save(update_fields=["is_read"])
        return Response({"detail": "ok"})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        updated = self._qs(request).filter(is_read=False).update(is_read=True)
        return Response({"updated": updated})

# ============================ DOMAIN LAYER ============================
# Per-user notifications. A row is one message delivered to one user; the bell
# in the top bar shows the unread count and the list.

from django.conf import settings
from django.db import models


class NotificationLevel(models.TextChoices):
    INFO = "info", "Info"
    SUCCESS = "success", "Success"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    level = models.CharField(max_length=20, choices=NotificationLevel.choices, default=NotificationLevel.INFO)
    link = models.CharField(max_length=300, blank=True)   # optional in-app route to open
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}: {self.title}"

    @staticmethod
    def notify(user, title, message="", level=NotificationLevel.INFO, link=""):
        """Convenience helper to raise a notification for a user."""
        return Notification.objects.create(
            user=user, title=title, message=message, level=level, link=link,
        )

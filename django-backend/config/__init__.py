# Make the Celery app import when Django starts so shared_task / @app.task work
# and `celery -A config` finds the instance.
from .celery import app as celery_app

__all__ = ("celery_app",)

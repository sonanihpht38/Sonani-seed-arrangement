"""
Celery application.

Broker + result backend come from Django settings (Redis by default). Task
modules are auto-discovered from every installed app's `tasks.py`, so a module
adds background work by dropping a `tasks.py` in its folder — same "new file, no
wiring" ergonomics as the rest of the project.

Run a worker:   celery -A config worker -l info
Run the beat:   celery -A config beat -l info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("sonani")

# All CELERY_* settings in Django settings become Celery config.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Trivial task to confirm the worker + broker round-trip works."""
    print(f"Celery request: {self.request!r}")

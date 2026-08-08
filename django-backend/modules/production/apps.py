import sys
import threading

from django.apps import AppConfig


def _warm_matplotlib():
    """Build matplotlib's Agg backend + font cache at startup (in the background) so
    the FIRST arrangement job doesn't pay the one-time lazy-initialization cost."""
    try:
        import os
        os.environ.setdefault("MPLBACKEND", "Agg")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot([0, 1], [0, 1])
        fig.canvas.draw()
        plt.close(fig)
    except Exception:
        pass


class ProductionConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "modules.production"
    label = "production"
    verbose_name = "Production"

    def ready(self):
        # Warm only in processes that actually render plates: the Celery worker
        # (arrangement jobs) and the web tier (Finalization regenerates images in
        # the request). Skip migrate/check/shell. Daemon thread, so startup and
        # the readiness probe never block on it.
        argv = " ".join(sys.argv)
        serving = any(k in argv for k in ("runserver", "gunicorn", "celery"))
        if serving:
            threading.Thread(target=_warm_matplotlib, daemon=True).start()

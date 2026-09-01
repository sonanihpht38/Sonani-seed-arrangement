"""Remove plate artifacts that no arrangement refers to any more.

Every arrangement job writes its plate PNGs and per-plate Excel to
MEDIA_ROOT/jobs/<job-id>/. Nothing ever removed them: the cache row that tracks
a job expires after 24 hours (see jobs.JOB_TTL) but the files it wrote outlive
it, so the directory grows for the life of the deployment. On the live host it
had reached 804 MB across 413 job directories.

BE CLEAR ABOUT WHAT THIS BUYS: it reclaims DISK. It does not make plate
generation faster — the packer never reads this directory — and it does not
reduce memory. It is housekeeping, and the reason to run it is that a full disk
takes the whole service down, not that the app is slow.

SAFETY. A directory is removed only when BOTH hold:

  * no TRN_SeedPlate row names it in any of its five path columns, so no
    arrangement in the history can still be displaying those images; and
  * it is older than --days (default 7), so a job running right now, or one a
    user is still stepping through Result -> Finalize -> Download, is never
    pulled out from under them.

Reports by default and writes nothing. Pass --delete to actually remove.

    python manage.py purge_job_artifacts                  # report only
    python manage.py purge_job_artifacts --days 30 --delete
"""

import os
import re
import shutil
import time

from django.conf import settings
from django.core.management.base import BaseCommand

# Job ids are "job-" + 12 hex chars (jobs.new_job_id). Anything else under
# jobs/ was not written by this app and is left alone.
_JOB_DIR = re.compile(r"^job-[0-9a-f]{12}$")


def _referenced_job_ids():
    """Every job id an arrangement still points at, from all five path columns."""
    from modules.production.models import SeedArrangePlate

    seen = set()
    rows = SeedArrangePlate.objects.values_list(
        "arrange_image_path", "machine_cut_image_path", "enhanced_image_path",
        "finalized_image_path", "excel_path",
    ).iterator()
    for paths in rows:
        for p in paths:
            if not p:
                continue
            # ".../jobs/<job-id>/..." — take the segment after "jobs".
            parts = str(p).replace("\\", "/").split("/")
            if "jobs" in parts:
                i = parts.index("jobs")
                if i + 1 < len(parts):
                    seen.add(parts[i + 1])
    return seen


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


class Command(BaseCommand):
    help = "Delete MEDIA_ROOT/jobs directories no arrangement references."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7,
                            help="Only consider directories older than this (default 7).")
        parser.add_argument("--delete", action="store_true",
                            help="Actually remove them. Without this, reports only.")

    def handle(self, *args, **options):
        root = os.path.join(settings.MEDIA_ROOT, "jobs")
        if not os.path.isdir(root):
            self.stdout.write(f"Nothing to do: {root} does not exist.")
            return

        keep = _referenced_job_ids()
        cutoff = time.time() - options["days"] * 86400

        stale, kept_ref, kept_young, freed = [], 0, 0, 0
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if not os.path.isdir(path) or not _JOB_DIR.match(name):
                continue
            if name in keep:
                kept_ref += 1
                continue
            try:
                if os.path.getmtime(path) > cutoff:
                    kept_young += 1
                    continue
            except OSError:
                continue
            size = _dir_size(path)
            stale.append((name, size))
            freed += size

        mb = freed / (1024 * 1024)
        self.stdout.write(
            f"{kept_ref} still referenced by an arrangement · "
            f"{kept_young} newer than {options['days']} days · "
            f"{len(stale)} removable ({mb:.1f} MB)")

        if not stale:
            return
        if not options["delete"]:
            for name, size in sorted(stale, key=lambda s: -s[1])[:10]:
                self.stdout.write(f"    {name}  {size / (1024 * 1024):6.1f} MB")
            if len(stale) > 10:
                self.stdout.write(f"    ... and {len(stale) - 10} more")
            self.stdout.write(self.style.WARNING(
                "Reported only. Re-run with --delete to remove them."))
            return

        removed = 0
        for name, _size in stale:
            try:
                shutil.rmtree(os.path.join(root, name))
                removed += 1
            except OSError as exc:
                self.stderr.write(self.style.WARNING(f"could not remove {name}: {exc}"))
        self.stdout.write(self.style.SUCCESS(
            f"Removed {removed} job directories, freeing {mb:.1f} MB."))

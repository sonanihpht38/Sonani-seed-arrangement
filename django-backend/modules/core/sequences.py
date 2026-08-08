# ===================== SHARED / CROSS-CUTTING: document numbering =====================
# Per-tenant, optionally period-scoped document numbers (INV-2026-00001).
#
#     number = SequenceService.next(tenant_id, "invoice", prefix="INV",
#                                   period=DocumentSequence.Period.YEAR)
#
# Call INSIDE the same transaction that inserts the document: the row lock
# (select_for_update -> UPDLOCK on SQL Server) serializes concurrent takers,
# and a rollback releases the number with the document. Numbers from genuinely
# aborted transactions are re-used only if they were never committed; gaps from
# committed-then-cancelled documents are accepted by design — gapless numbering
# under concurrency would serialize the whole tenant's writes.

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import DocumentSequence


class SequenceService:
    @staticmethod
    def next(tenant_id, code, *, prefix="", padding=5, period=None, when=None):
        period = period or DocumentSequence.Period.NONE
        when = when or timezone.now()
        if period == DocumentSequence.Period.YEAR:
            period_key = f"{when.year}"
        elif period == DocumentSequence.Period.MONTH:
            period_key = f"{when.year}-{when.month:02d}"
        else:
            period_key = ""

        with transaction.atomic():
            try:
                row, _ = (DocumentSequence.objects.select_for_update()
                          .get_or_create(tenant_id=tenant_id, code=code, period_key=period_key,
                                         defaults={"prefix": prefix, "padding": padding,
                                                   "period": period}))
            except IntegrityError:
                # Lost a concurrent-create race; the row exists now — lock it.
                row = (DocumentSequence.objects.select_for_update()
                       .get(tenant_id=tenant_id, code=code, period_key=period_key))
            number = row.next_value
            row.next_value = number + 1
            row.save(update_fields=["next_value"])

        parts = [p for p in (row.prefix, period_key) if p]
        parts.append(f"{number:0{row.padding}d}")
        return "-".join(parts)

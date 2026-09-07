# ===================== INFRASTRUCTURE LAYER: repository =====================
# The only place that queries the DiamondElement seed tables (TRN_Batch,
# TRN_SeedData). Both models use the default connection.

from django.db.models import Count

from .models import Batch, SeedData


class BatchRepository:
    @staticmethod
    def existing_nos(wanted):
        """Which of `wanted` BatchNos already exist in TRN_Batch (stripped)."""
        return {
            (b or "").strip()
            for b in Batch.objects.filter(batch_no__in=list(wanted)).values_list("batch_no", flat=True)
            if b and b.strip()
        }

    @staticmethod
    def list_with_counts():
        """Every batch plus how many AVAILABLE seeds reference it
        (TRN_SeedData.Batch_ID). Batch_ID is a plain GUID column (no Django FK),
        so counts are grouped separately and joined in Python.

        Available, not total. This count is what Batch Selection shows on each
        card, what it sums into "N seeds selected", and what it greys a batch out
        on — so it is the user's picture of the pool they are about to pack from.
        Counting every row made it disagree with the packer, which excludes seeds
        already on an assigned plate: a batch of 3 consumed stones still read
        "3 seeds", inviting the user to select stock that could not be placed.
        The packer was never at risk of double-allocating them — it filters the
        same way and consume_plate refuses a stone another run holds — but the
        screen said otherwise, which is its own kind of wrong.

        `exclude(is_used=True)`, NOT `filter(is_used=False)`: ISUsed is NULL for
        a seed nobody has consumed, and filtering on False would drop every one
        of those, i.e. the entire available pool. Same reason engine_runner
        writes it this way; the two must agree or this bug simply changes sides.
        """
        counts = {
            row["batch_id"]: row["n"]
            for row in SeedData.objects.exclude(batch_id__isnull=True)
            .exclude(is_used=True)
            .values("batch_id").annotate(n=Count("seed_id"))
        }
        return [
            {
                "batch_id": b.batch_id,
                "batch_no": b.batch_no,
                "seed_count": counts.get(b.batch_id, 0),
                "is_active": bool(b.is_active),
            }
            for b in Batch.objects.all().order_by("batch_no")
        ]

    @staticmethod
    def bulk_create(batches):
        Batch.objects.bulk_create(batches)

    @staticmethod
    def id_by_no():
        """BatchNo → Batch_ID for every batch (stripped keys)."""
        return {
            (b or "").strip(): bid
            for bid, b in Batch.objects.values_list("batch_id", "batch_no")
            if b and b.strip()
        }


class SeedRepository:
    @staticmethod
    def existing_stock_nos():
        """StockNos already present in TRN_SeedData (stripped)."""
        return {
            s.strip()
            for s in SeedData.objects.exclude(stock_no__isnull=True).values_list("stock_no", flat=True)
            if s and s.strip()
        }

    @staticmethod
    def bulk_create(seeds, batch_size=500):
        SeedData.objects.bulk_create(seeds, batch_size=batch_size)

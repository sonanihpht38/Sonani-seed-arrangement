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
        """Every batch plus how many seeds reference it (TRN_SeedData.Batch_ID).
        Batch_ID is a plain GUID column (no Django FK), so counts are grouped
        separately and joined in Python."""
        counts = {
            row["batch_id"]: row["n"]
            for row in SeedData.objects.exclude(batch_id__isnull=True)
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

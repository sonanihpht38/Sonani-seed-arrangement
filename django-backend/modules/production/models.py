# ============================ DOMAIN LAYER ============================
# Production module — the diamond plate-arrangement workflow.
#
# These models map tables that Django does NOT own: managed = False, so it only
# reads/writes rows and never creates/alters/drops them. They live on the
# `default` connection alongside the rest of the ERP; create them once with
# `manage.py init_production_schema` (sql/create_*.sql).
#
# Because `managed = False` there are no migrations for this app — the DDL in
# sql/ is the schema's source of truth, and it is idempotent.
#
# Seed import (workflow form 1) uses two of them: TRN_Batch (the batch master)
# and TRN_SeedData (the imported seeds). Later forms add the arrangement / plate /
# detail tables.
#
# These tables are NOT tenant-scoped (no tenant column) — they model a single
# physical production line, not per-company data. Access is gated by form
# permission, the same as every other module.

import uuid

from django.db import models


# Canonical DomainError lives in modules.core; re-exported for existing imports
# (modules.access does the same). It MUST be that class and not a local copy:
# config.settings' DRF EXCEPTION_HANDLER renders DomainError via an isinstance
# check against modules.core.exceptions.DomainError, so a private subclass here
# silently failed that check and any error not caught by an explicit per-view
# try/except surfaced as HTTP 500 instead of a clean {"detail": ...} 400.
from modules.core.exceptions import DomainError  # noqa: E402,F401


class UniqueIdentifierField(models.UUIDField):
    """UUIDField that writes the value as a DASHED 36-char string.

    Django's UUIDField sends `uuid.hex` (32 chars, no dashes) because
    mssql-django maps UUIDField to char(32) — which does NOT convert into a real
    SQL Server `uniqueidentifier` column (it needs the 8-4-4-4-12 dashed form) and
    raises a "conversion failed … to uniqueidentifier" error on insert. Sending
    `str(uuid)` fixes it; reads still come back as UUID objects.
    """

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = self.to_python(value)
        return str(value)  # dashed 36-char → valid uniqueidentifier literal


class Batch(models.Model):
    """DiamondElement.dbo.TRN_Batch — the batch master (one row per BatchNo).
    On import a row is inserted here for every new BatchNo (giving it a Batch_ID);
    existing batches are left untouched."""

    batch_id = UniqueIdentifierField(primary_key=True, default=uuid.uuid4, db_column="Batch_ID")
    batch_no = models.CharField(max_length=50, null=True, blank=True, db_column="BatchNo")
    is_active = models.BooleanField(null=True, blank=True, default=True, db_column="ISActive")
    remarks = models.CharField(max_length=200, null=True, blank=True, db_column="Remarks")
    entry_date = models.DateTimeField(null=True, blank=True, db_column="EntryDate")
    entry_by = models.IntegerField(null=True, blank=True, db_column="EntryBy")
    update_date = models.DateTimeField(null=True, blank=True, db_column="UpdateDate")
    update_by = models.IntegerField(null=True, blank=True, db_column="UpdateBy")

    class Meta:
        managed = False
        db_table = "TRN_Batch"

    def __str__(self):
        return self.batch_no or str(self.batch_id)


class SeedData(models.Model):
    """DiamondElement.dbo.TRN_SeedData — the imported seeds. The uploaded Excel
    datasheet is imported into it; column order in the sheet is
    BatchNo, StockNo, Pcs, Cts, Length, Width, Height."""

    seed_id = UniqueIdentifierField(primary_key=True, default=uuid.uuid4, db_column="Seed_ID")
    batch_id = UniqueIdentifierField(null=True, blank=True, db_column="Batch_ID")  # FK → TRN_Batch.Batch_ID
    stock_no = models.CharField(max_length=50, null=True, blank=True, db_column="StockNo")
    pcs = models.IntegerField(null=True, blank=True, db_column="Pcs")
    cts = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Cts")
    length = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Length")
    width = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Width")
    height = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Height")
    # True outline of an IRREGULAR seed — a blank with one or more corners cut
    # off — as a JSON array of [x, y] pairs in mm, re-origined to (0, 0). NULL
    # (the normal case) means "plain Length x Width rectangle", which is the
    # behaviour that predates this column. Written by the importer only after
    # shapes.validate_corners() passes; read by the Max Coverage packer only.
    corners_json = models.CharField(max_length=4000, null=True, blank=True, db_column="CornersJSON")
    is_used = models.BooleanField(null=True, blank=True, db_column="ISUsed")
    used_id = UniqueIdentifierField(null=True, blank=True, db_column="Used_ID")
    entry_date = models.DateTimeField(null=True, blank=True, db_column="EntryDate")
    entry_by = models.IntegerField(null=True, blank=True, db_column="EntryBy")
    update_date = models.DateTimeField(null=True, blank=True, db_column="UpdateDate")
    update_by = models.IntegerField(null=True, blank=True, db_column="UpdateBy")

    class Meta:
        managed = False
        db_table = "TRN_SeedData"

    def __str__(self):
        return str(self.stock_no or self.seed_id)


class DummySeedData(models.Model):
    """DiamondElement.dbo.TRN_DummySeedData — synthetic filler ("dummy") seeds from
    Machine-Cut Fill. Same shape as TRN_SeedData; one row per placed dummy."""

    seed_id = UniqueIdentifierField(primary_key=True, default=uuid.uuid4, db_column="Seed_ID")
    batch_id = UniqueIdentifierField(null=True, blank=True, db_column="Batch_ID")
    stock_no = models.CharField(max_length=50, null=True, blank=True, db_column="StockNo")
    pcs = models.IntegerField(null=True, blank=True, db_column="Pcs")
    cts = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Cts")
    length = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Length")
    width = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Width")
    height = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Height")
    entry_date = models.DateTimeField(null=True, blank=True, db_column="EntryDate")
    entry_by = models.IntegerField(null=True, blank=True, db_column="EntryBy")
    update_date = models.DateTimeField(null=True, blank=True, db_column="UpdateDate")
    update_by = models.IntegerField(null=True, blank=True, db_column="UpdateBy")

    class Meta:
        managed = False
        db_table = "TRN_DummySeedData"


class SeedArrange(models.Model):
    """TRN_SeedArrange — one HEADER row per arrangement run (plate count, avg fill %,
    and the input criteria it was generated with)."""

    arrange_id = UniqueIdentifierField(primary_key=True, default=uuid.uuid4, db_column="Arrange_ID")
    is_active = models.BooleanField(null=True, blank=True, default=True, db_column="ISActive")
    plate_no = models.IntegerField(null=True, blank=True, db_column="PlateNo")
    average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column="Average")
    mode = models.CharField(max_length=20, null=True, blank=True, db_column="Mode")
    shape = models.CharField(max_length=20, null=True, blank=True, db_column="Shape")
    square_tol = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True, db_column="SquareTol")
    thickness_min = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True, db_column="ThicknessMin")
    thickness_max = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True, db_column="ThicknessMax")
    # Seed-width band the run was generated with, in mm — the SHORT side of a
    # seed (see engine_runner.seed_width). NULL at either end means "unbounded
    # on that end", which is also what every row written before the criteria
    # form gained these fields carries.
    width_min = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True, db_column="WidthMin")
    width_max = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True, db_column="WidthMax")
    plate_diameter = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, db_column="PlateDiameter")
    margin = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, db_column="Margin")
    min_filler_size = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, db_column="MinFillerSize")
    exclude_stocks = models.TextField(null=True, blank=True, db_column="ExcludeStocks")
    batches = models.TextField(null=True, blank=True, db_column="Batches")
    entry_date = models.DateField(null=True, blank=True, db_column="EntryDate")
    entry_by = models.IntegerField(null=True, blank=True, db_column="EntryBy")
    is_finalized = models.BooleanField(null=True, blank=True, db_column="IsFinalized")
    finalized_by_user = models.BooleanField(null=True, blank=True, db_column="FinalizedByUser")
    finalized_by = models.IntegerField(null=True, blank=True, db_column="FinalizedBy")
    finalized_date = models.DateTimeField(null=True, blank=True, db_column="FinalizedDate")

    class Meta:
        managed = False
        db_table = "TRN_SeedArrange"


class SeedPlate(models.Model):
    """MST_SeedPlate — the reusable plate-name master (one row per plate size).
    Plate_ID is an IDENTITY column."""

    plate_id = models.AutoField(primary_key=True, db_column="Plate_ID")
    plate_name = models.CharField(max_length=50, null=True, blank=True, db_column="PlateName")
    diameter = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="Diameter")
    is_active = models.BooleanField(null=True, blank=True, default=True, db_column="ISActive")
    is_used = models.BooleanField(null=True, blank=True, db_column="ISUsed")
    is_released = models.BooleanField(null=True, blank=True, db_column="IsReleased")
    entry_date = models.DateTimeField(null=True, blank=True, db_column="EntryDate")
    entry_by = models.IntegerField(null=True, blank=True, db_column="EntryBy")
    update_date = models.DateTimeField(null=True, blank=True, db_column="UpdateDate")
    update_by = models.IntegerField(null=True, blank=True, db_column="UpdateBy")

    class Meta:
        managed = False
        db_table = "MST_SeedPlate"


class SeedArrangePlate(models.Model):
    """TRN_SeedPlate — one row per PLATE per arrangement: per-plate summary + the file
    paths of the Arrange / Machine-Cut / Finalized images, plus covered/total area."""

    arrange_plate_id = UniqueIdentifierField(primary_key=True, default=uuid.uuid4, db_column="SeedPlate_ID")
    arrange_id = UniqueIdentifierField(null=True, blank=True, db_column="Arrange_ID")
    plate_no = models.IntegerField(null=True, blank=True, db_column="PlateNo")
    plate_id = models.IntegerField(null=True, blank=True, db_column="Plate_ID")
    plate_name = models.CharField(max_length=100, null=True, blank=True, db_column="PlateName")
    arrange_image_path = models.CharField(max_length=500, null=True, blank=True, db_column="ArrangeImagePath")
    machine_cut_image_path = models.CharField(max_length=500, null=True, blank=True, db_column="MachineCutImagePath")
    enhanced_image_path = models.CharField(max_length=500, null=True, blank=True, db_column="EnhancedImagePath")
    finalized_image_path = models.CharField(max_length=500, null=True, blank=True, db_column="FinalizedImagePath")
    excel_path = models.CharField(max_length=500, null=True, blank=True, db_column="ExcelPath")
    arrange_fill_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column="ArrangeFillPct")
    machine_fill_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column="MachineFillPct")
    enhanced_fill_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column="EnhancedFillPct")
    finalized_fill_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column="FinalizedFillPct")
    real_seed_count = models.IntegerField(null=True, blank=True, db_column="RealSeedCount")
    dummy_count = models.IntegerField(null=True, blank=True, db_column="DummyCount")
    total_area_mm2 = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="TotalAreaMM2")
    arrange_covered_mm2 = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="ArrangeCoveredMM2")
    machine_covered_mm2 = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="MachineCoveredMM2")
    finalized_covered_mm2 = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="FinalizedCoveredMM2")
    entry_date = models.DateTimeField(null=True, blank=True, db_column="EntryDate")
    entry_by = models.IntegerField(null=True, blank=True, db_column="EntryBy")
    update_date = models.DateTimeField(null=True, blank=True, db_column="UpdateDate")
    update_by = models.IntegerField(null=True, blank=True, db_column="UpdateBy")

    class Meta:
        managed = False
        db_table = "TRN_SeedPlate"


class SeedArrangeDetail(models.Model):
    """TRN_SeedArrangeDetails — one row per placed seed. SeedType: 0 = real
    (TRN_SeedData), 1 = dummy (TRN_DummySeedData)."""

    detail_id = UniqueIdentifierField(primary_key=True, default=uuid.uuid4, db_column="Detail_ID")
    arrange_id = UniqueIdentifierField(null=True, blank=True, db_column="Arrange_ID")
    seed_type = models.BooleanField(null=True, blank=True, db_column="SeedType")
    seed_id = UniqueIdentifierField(null=True, blank=True, db_column="Seed_ID")
    plate_id = models.IntegerField(null=True, blank=True, db_column="Plate_ID")
    is_recommended = models.BooleanField(null=True, blank=True, db_column="IsRecommended")
    is_final = models.BooleanField(null=True, blank=True, db_column="IsFinal")
    replaces_seed_id = UniqueIdentifierField(null=True, blank=True, db_column="ReplacesSeed_ID")
    # Which processing method placed this seed ("arrange" / "machinefill" / "enhanced").
    # NULL on rows written before per-method detail saving existed.
    method = models.CharField(max_length=20, null=True, blank=True, db_column="Method")
    # Max Coverage only: how much of the seat was trimmed off by the edge cut.
    cut_area_mm2 = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column="CutAreaMM2")
    cut_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column="CutPct")

    class Meta:
        managed = False
        db_table = "TRN_SeedArrangeDetails"

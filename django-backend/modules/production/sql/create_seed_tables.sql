-- ============================================================================
-- Production module — seed schema.
-- Creates the two tables the Seed Import endpoint reads/writes, in the ERP's
-- default database. Columns match modules/production/models.py.
-- Applied by: python manage.py init_production_schema
--
-- Idempotent: guarded with IF OBJECT_ID(...) IS NULL, so it is safe to run more
-- than once. Deliberately NO triggers and NO enforced FK — the Batch_ID → Batch
-- relationship is logical (the importer inserts batches before their seeds); this
-- avoids the trigger / insert-ordering issues seen on the original database.
-- ============================================================================

IF OBJECT_ID('dbo.TRN_Batch', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRN_Batch (
        Batch_ID   uniqueidentifier NOT NULL,
        BatchNo    nvarchar(50)     NULL,
        ISActive   bit              NULL,
        Remarks    nvarchar(200)    NULL,
        EntryDate  datetime2(7)     NULL,
        EntryBy    int              NULL,
        UpdateDate datetime2(7)     NULL,
        UpdateBy   int              NULL,
        CONSTRAINT PK_TRN_Batch PRIMARY KEY CLUSTERED (Batch_ID)
    );
    CREATE INDEX IX_TRN_Batch_BatchNo ON dbo.TRN_Batch (BatchNo);
END;
GO

IF OBJECT_ID('dbo.TRN_SeedData', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRN_SeedData (
        Seed_ID    uniqueidentifier NOT NULL,
        Batch_ID   uniqueidentifier NULL,
        StockNo    nvarchar(50)     NULL,
        Pcs        int              NULL,
        Cts        decimal(18, 2)   NULL,
        Length     decimal(18, 2)   NULL,
        Width      decimal(18, 2)   NULL,
        Height     decimal(18, 2)   NULL,
        ISUsed     bit              NULL,
        Used_ID    uniqueidentifier NULL,
        EntryDate  datetime2(7)     NULL,
        EntryBy    int              NULL,
        UpdateDate datetime2(7)     NULL,
        UpdateBy   int              NULL,
        CONSTRAINT PK_TRN_SeedData PRIMARY KEY CLUSTERED (Seed_ID)
    );
    CREATE INDEX IX_TRN_SeedData_StockNo ON dbo.TRN_SeedData (StockNo);
    CREATE INDEX IX_TRN_SeedData_Batch_ID ON dbo.TRN_SeedData (Batch_ID);
END;
GO

-- ---------------------------------------------------------------------------
-- Back-fill: CornersJSON — the true outline of an IRREGULAR seed (one that is
-- not a plain Length x Width rectangle, e.g. a blank with a corner cut off).
--
-- JSON array of [x, y] pairs in mm, re-origined so the outline's bottom-left is
-- (0, 0):  [[0,0],[12.4,0],[12.4,6.5],[9.2,9.8],[0,9.8]]
--
-- NULL is the normal case and means "plain Length x Width rectangle" — exactly
-- the behaviour before this column existed, so every pre-existing row is
-- unaffected. Written by the seed importer only after the corner list passes
-- modules/production/shapes.validate_corners(); read by the Max Coverage packer
-- only. The Arrange packer never looks at it.
--
-- nvarchar(4000) rather than (max): 12 corners is the validated ceiling
-- (~300 chars), so this stays an in-row column with no LOB overhead.
-- ---------------------------------------------------------------------------
IF COL_LENGTH('dbo.TRN_SeedData', 'CornersJSON') IS NULL
    ALTER TABLE dbo.TRN_SeedData ADD CornersJSON nvarchar(4000) NULL;
GO

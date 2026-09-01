-- ============================================================================
-- Production module — arrangement schema.
-- The 5 tables the arrangement job (Form 5) and finalize (Form 6) read/write, in
-- the ERP's default database. Columns match models.py.
-- Idempotent (guarded with IF OBJECT_ID(...) IS NULL). No triggers/FKs.
-- Applied by: python manage.py init_production_schema
-- ============================================================================

IF OBJECT_ID('dbo.TRN_DummySeedData', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRN_DummySeedData (
        Seed_ID    uniqueidentifier NOT NULL,
        Batch_ID   uniqueidentifier NULL,
        StockNo    nvarchar(50)     NULL,
        Pcs        int              NULL,
        Cts        decimal(18, 2)   NULL,
        Length     decimal(18, 2)   NULL,
        Width      decimal(18, 2)   NULL,
        Height     decimal(18, 2)   NULL,
        EntryDate  datetime2(7)     NULL,
        EntryBy    int              NULL,
        UpdateDate datetime2(7)     NULL,
        UpdateBy   int              NULL,
        CONSTRAINT PK_TRN_DummySeedData PRIMARY KEY CLUSTERED (Seed_ID)
    );
END;
GO

IF OBJECT_ID('dbo.TRN_SeedArrange', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRN_SeedArrange (
        Arrange_ID      uniqueidentifier NOT NULL,
        ISActive        bit              NULL,
        PlateNo         int              NULL,
        Average         decimal(5, 2)    NULL,
        Mode            nvarchar(20)     NULL,
        Shape           nvarchar(20)     NULL,
        SquareTol       decimal(9, 3)    NULL,
        ThicknessMin    decimal(9, 3)    NULL,
        ThicknessMax    decimal(9, 3)    NULL,
        PlateDiameter   decimal(9, 2)    NULL,
        Margin          decimal(9, 2)    NULL,
        MinFillerSize   decimal(9, 2)    NULL,
        ExcludeStocks   nvarchar(max)    NULL,
        Batches         nvarchar(max)    NULL,
        EntryDate       date             NULL,
        EntryBy         int              NULL,
        IsFinalized     bit              NULL,
        FinalizedByUser bit              NULL,
        FinalizedBy     int              NULL,
        FinalizedDate   datetime2(7)     NULL,
        CONSTRAINT PK_TRN_SeedArrange PRIMARY KEY CLUSTERED (Arrange_ID)
    );
END;
GO

IF OBJECT_ID('dbo.MST_SeedPlate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.MST_SeedPlate (
        Plate_ID   int IDENTITY(1,1) NOT NULL,
        PlateName  nvarchar(50)   NULL,
        Diameter   decimal(18, 2) NULL,
        ISActive   bit            NULL,
        ISUsed     bit            NULL,
        IsReleased bit            NULL,
        EntryDate  datetime2(7)   NULL,
        EntryBy    int            NULL,
        UpdateDate datetime2(7)   NULL,
        UpdateBy   int            NULL,
        CONSTRAINT PK_MST_SeedPlate PRIMARY KEY CLUSTERED (Plate_ID)
    );
END;
GO

IF OBJECT_ID('dbo.TRN_SeedPlate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRN_SeedPlate (
        SeedPlate_ID        uniqueidentifier NOT NULL,
        Arrange_ID          uniqueidentifier NULL,
        PlateNo             int              NULL,
        Plate_ID            int              NULL,
        PlateName           nvarchar(100)    NULL,
        ArrangeImagePath    nvarchar(500)    NULL,
        MachineCutImagePath nvarchar(500)    NULL,
        EnhancedImagePath   nvarchar(500)    NULL,
        FinalizedImagePath  nvarchar(500)    NULL,
        ExcelPath           nvarchar(500)    NULL,
        ArrangeFillPct      decimal(5, 2)    NULL,
        MachineFillPct      decimal(5, 2)    NULL,
        EnhancedFillPct     decimal(5, 2)    NULL,
        FinalizedFillPct    decimal(5, 2)    NULL,
        RealSeedCount       int              NULL,
        DummyCount          int              NULL,
        TotalAreaMM2        decimal(18, 2)   NULL,
        ArrangeCoveredMM2   decimal(18, 2)   NULL,
        MachineCoveredMM2   decimal(18, 2)   NULL,
        FinalizedCoveredMM2 decimal(18, 2)   NULL,
        EntryDate           datetime2(7)     NULL,
        EntryBy             int              NULL,
        UpdateDate          datetime2(7)     NULL,
        UpdateBy            int              NULL,
        CONSTRAINT PK_TRN_SeedPlate PRIMARY KEY CLUSTERED (SeedPlate_ID)
    );
    CREATE INDEX IX_TRN_SeedPlate_Arrange ON dbo.TRN_SeedPlate (Arrange_ID);
END;
GO

IF OBJECT_ID('dbo.TRN_SeedArrangeDetails', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRN_SeedArrangeDetails (
        Detail_ID       uniqueidentifier NOT NULL,
        Arrange_ID      uniqueidentifier NULL,
        SeedType        bit              NULL,
        Seed_ID         uniqueidentifier NULL,
        Plate_ID        int              NULL,
        IsRecommended   bit              NULL,
        IsFinal         bit              NULL,
        ReplacesSeed_ID uniqueidentifier NULL,
        Method          nvarchar(20)     NULL,
        CutAreaMM2      decimal(18, 2)   NULL,
        CutPct          decimal(5, 2)    NULL,
        CONSTRAINT PK_TRN_SeedArrangeDetails PRIMARY KEY CLUSTERED (Detail_ID)
    );
    CREATE INDEX IX_TRN_SeedArrangeDetails_Arrange ON dbo.TRN_SeedArrangeDetails (Arrange_ID);
END;
GO

-- ---------------------------------------------------------------------------
-- Column back-fill. The five columns below were added to the schema after the
-- original CREATE scripts were written, so a database created from an older
-- version of this file is missing them and the arrangement job fails on insert
-- with "Invalid column name 'Method'". Guarded per column, so this is a no-op on
-- an up-to-date database and safe to re-run.
-- ---------------------------------------------------------------------------
IF COL_LENGTH('dbo.TRN_SeedPlate', 'EnhancedImagePath') IS NULL
    ALTER TABLE dbo.TRN_SeedPlate ADD EnhancedImagePath nvarchar(500) NULL;
GO
IF COL_LENGTH('dbo.TRN_SeedPlate', 'EnhancedFillPct') IS NULL
    ALTER TABLE dbo.TRN_SeedPlate ADD EnhancedFillPct decimal(5, 2) NULL;
GO
IF COL_LENGTH('dbo.TRN_SeedArrangeDetails', 'Method') IS NULL
    ALTER TABLE dbo.TRN_SeedArrangeDetails ADD Method nvarchar(20) NULL;
GO
IF COL_LENGTH('dbo.TRN_SeedArrangeDetails', 'CutAreaMM2') IS NULL
    ALTER TABLE dbo.TRN_SeedArrangeDetails ADD CutAreaMM2 decimal(18, 2) NULL;
GO
IF COL_LENGTH('dbo.TRN_SeedArrangeDetails', 'CutPct') IS NULL
    ALTER TABLE dbo.TRN_SeedArrangeDetails ADD CutPct decimal(5, 2) NULL;
GO

-- Seed-width band (mm) the run was generated with — the SHORT side of a seed,
-- min(Length, Width). NULL means unbounded at that end, which is what every row
-- written before the criteria form gained these fields carries, so existing
-- history keeps its exact meaning.
IF COL_LENGTH('dbo.TRN_SeedArrange', 'WidthMin') IS NULL
    ALTER TABLE dbo.TRN_SeedArrange ADD WidthMin decimal(9, 3) NULL;
GO
IF COL_LENGTH('dbo.TRN_SeedArrange', 'WidthMax') IS NULL
    ALTER TABLE dbo.TRN_SeedArrange ADD WidthMax decimal(9, 3) NULL;
GO

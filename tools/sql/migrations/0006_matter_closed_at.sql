
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matters' AND COLUMN_NAME = 'closed_at'
)
    ALTER TABLE dbo.matters ADD closed_at DATETIME2 NULL
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matters' AND COLUMN_NAME = 'closed_by'
)
    ALTER TABLE dbo.matters ADD closed_by NVARCHAR(100) NULL
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matters' AND COLUMN_NAME = 'closed_notes'
)
    ALTER TABLE dbo.matters ADD closed_notes NVARCHAR(500) NULL
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.matters') AND name = 'IX_matters_closed_at'
)
    CREATE INDEX IX_matters_closed_at ON dbo.matters (closed_at)
GO

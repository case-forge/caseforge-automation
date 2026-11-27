
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matters' AND COLUMN_NAME = 'relationship_start'
)
    ALTER TABLE dbo.matters ADD relationship_start NVARCHAR(100) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matters' AND COLUMN_NAME = 'relationship_end'
)
    ALTER TABLE dbo.matters ADD relationship_end NVARCHAR(100) NULL;
GO

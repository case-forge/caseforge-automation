
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matters' AND COLUMN_NAME = 'appropriate_adult'
)
    ALTER TABLE dbo.matters ADD appropriate_adult NVARCHAR(255) NULL;
GO


IF OBJECT_ID(N'dbo.matter_children', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.matter_children (
        child_id INT IDENTITY(1,1) PRIMARY KEY,
        matter_id INT NOT NULL,
        child_name NVARCHAR(255) NULL,
        dob_iso NVARCHAR(40) NULL,
        gender NVARCHAR(80) NULL,
        parental_responsibility NVARCHAR(500) NULL,
        notes NVARCHAR(MAX) NULL,
        source NVARCHAR(100) NULL,
        created_utc DATETIME2 NULL,
        updated_utc DATETIME2 NULL
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matter_children' AND COLUMN_NAME = 'gender'
)
    ALTER TABLE dbo.matter_children ADD gender NVARCHAR(80) NULL;
GO

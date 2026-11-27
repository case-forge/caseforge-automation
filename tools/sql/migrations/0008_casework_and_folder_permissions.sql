
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matter_permissions' AND COLUMN_NAME = 'allow_casework'
)
    ALTER TABLE dbo.matter_permissions ADD allow_casework BIT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matter_permissions' AND COLUMN_NAME = 'casework_set_at'
)
    ALTER TABLE dbo.matter_permissions ADD casework_set_at DATETIME2 NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matter_permissions' AND COLUMN_NAME = 'casework_set_by'
)
    ALTER TABLE dbo.matter_permissions ADD casework_set_by NVARCHAR(100) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matter_permissions' AND COLUMN_NAME = 'allow_folder_create'
)
    ALTER TABLE dbo.matter_permissions ADD allow_folder_create BIT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matter_permissions' AND COLUMN_NAME = 'folder_create_set_at'
)
    ALTER TABLE dbo.matter_permissions ADD folder_create_set_at DATETIME2 NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'matter_permissions' AND COLUMN_NAME = 'folder_create_set_by'
)
    ALTER TABLE dbo.matter_permissions ADD folder_create_set_by NVARCHAR(100) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_matter_permissions_allow_casework'
      AND object_id = OBJECT_ID('dbo.matter_permissions')
)
    CREATE INDEX ix_matter_permissions_allow_casework
    ON dbo.matter_permissions (allow_casework);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_matter_permissions_allow_folder_create'
      AND object_id = OBJECT_ID('dbo.matter_permissions')
)
    CREATE INDEX ix_matter_permissions_allow_folder_create
    ON dbo.matter_permissions (allow_folder_create);
GO

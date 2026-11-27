
IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE name = 'matter_folder_locations' AND schema_id = SCHEMA_ID('dbo')
)
BEGIN
    CREATE TABLE dbo.matter_folder_locations (
        matter_id              INT            NOT NULL,
        client_name            NVARCHAR(300)  NULL,
        matter_name            NVARCHAR(300)  NULL,
        storage_root           NVARCHAR(200)  NULL,
        site_id                NVARCHAR(300)  NULL,
        drive_id               NVARCHAR(300)  NULL,
        matter_folder_id       NVARCHAR(300)  NULL,
        matter_folder_path     NVARCHAR(1000) NULL,
        matter_folder_name     NVARCHAR(300)  NULL,
        attendance_folder_id   NVARCHAR(300)  NULL,
        attendance_folder_name NVARCHAR(300)  NULL,
        source                 NVARCHAR(80)   NULL,
        last_verified_utc      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        created_at             DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at             DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT pk_matter_folder_locations PRIMARY KEY (matter_id),
        CONSTRAINT fk_matter_folder_locations_matter
            FOREIGN KEY (matter_id) REFERENCES dbo.matters (matter_id)
            ON DELETE CASCADE
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_matter_folder_locations_client_name'
      AND object_id = OBJECT_ID('dbo.matter_folder_locations')
)
BEGIN
    CREATE INDEX ix_matter_folder_locations_client_name
    ON dbo.matter_folder_locations (client_name);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_matter_folder_locations_folder_name'
      AND object_id = OBJECT_ID('dbo.matter_folder_locations')
)
BEGIN
    CREATE INDEX ix_matter_folder_locations_folder_name
    ON dbo.matter_folder_locations (matter_folder_name);
END;
GO

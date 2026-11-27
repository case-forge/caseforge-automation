IF OBJECT_ID('dbo.runtime_event_hourly', 'U') IS NULL
BEGIN

    CREATE TABLE dbo.runtime_event_hourly (
        hour_utc         NVARCHAR(13)  NOT NULL,
        runtime_label    NVARCHAR(64)  NOT NULL,
        event_name       NVARCHAR(64)  NOT NULL,
        events           INT           NOT NULL DEFAULT 0,
        errors           INT           NOT NULL DEFAULT 0,
        first_timestamp  NVARCHAR(32)  NULL,
        last_timestamp   NVARCHAR(32)  NULL,
        updated_utc      NVARCHAR(32)  NULL,
        inserted_utc     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_runtime_event_hourly
            PRIMARY KEY (hour_utc, runtime_label, event_name)
    )
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.runtime_event_hourly')
      AND name = 'IX_runtime_event_hourly_updated_utc'
)
    CREATE INDEX IX_runtime_event_hourly_updated_utc
        ON dbo.runtime_event_hourly (updated_utc DESC)
GO

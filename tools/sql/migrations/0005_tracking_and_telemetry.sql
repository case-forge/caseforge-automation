IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME='matter_live_status' AND COLUMN_NAME='draft_order_status'
)
    ALTER TABLE dbo.matter_live_status ADD draft_order_status NVARCHAR(100) NULL
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME='matter_live_status' AND COLUMN_NAME='waiting_for_sealed_order'
)
    ALTER TABLE dbo.matter_live_status ADD waiting_for_sealed_order BIT NOT NULL DEFAULT 0
GO

UPDATE dbo.matter_live_status
SET waiting_for_sealed_order = 1
WHERE (sealed_order_status LIKE '%await%' OR sealed_order_status LIKE '%pending%')
   OR (order_status LIKE '%granted%' AND (sealed_order_status IS NULL OR sealed_order_status = 'none'))
GO

IF OBJECT_ID('dbo.graph_api_calls_daily', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.graph_api_calls_daily (
        day_utc         NVARCHAR(10)  NOT NULL,
        call_type       NVARCHAR(64)  NOT NULL,
        total_calls     INT           NOT NULL DEFAULT 0,
        success_count   INT           NOT NULL DEFAULT 0,
        error_count     INT           NOT NULL DEFAULT 0,
        avg_duration_ms INT           NULL,
        runtime_label   NVARCHAR(64)  NULL,
        inserted_utc    DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_graph_api_calls_daily PRIMARY KEY (day_utc, call_type)
    )
END
GO

IF OBJECT_ID('dbo.client_search_events', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_search_events (
        event_id         NVARCHAR(64)  NOT NULL,
        recorded_at      NVARCHAR(32)  NOT NULL,
        query_kind       NVARCHAR(64)  NULL,
        resolver_success BIT           NOT NULL DEFAULT 0,
        confidence_hint  NVARCHAR(32)  NULL,
        is_typo          BIT           NOT NULL DEFAULT 0,
        runtime_label    NVARCHAR(64)  NULL,
        inserted_utc     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_client_search_events PRIMARY KEY (event_id)
    )
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.client_search_events')
      AND name = 'IX_client_search_events_recorded_at'
)
    CREATE INDEX IX_client_search_events_recorded_at
        ON dbo.client_search_events (recorded_at DESC)
GO

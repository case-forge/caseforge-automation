IF OBJECT_ID('dbo.runtime_activation_events', 'U') IS NULL
BEGIN

    CREATE TABLE dbo.runtime_activation_events (
        event_id         NVARCHAR(64)   NOT NULL,
        event            NVARCHAR(64)   NOT NULL,
        run_utc          NVARCHAR(32)   NOT NULL,
        run_end_utc      NVARCHAR(32)   NULL,
        runtime_label    NVARCHAR(64)   NULL,
        model_label      NVARCHAR(128)  NULL,
        command          NVARCHAR(512)  NULL,
        sub_results_json NVARCHAR(MAX)  NULL,
        inserted_utc     DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_runtime_activation_events PRIMARY KEY (event_id)
    )
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.runtime_activation_events')
      AND name = 'IX_runtime_activation_events_run_utc'
)
    CREATE INDEX IX_runtime_activation_events_run_utc
        ON dbo.runtime_activation_events (run_utc DESC)
GO

IF OBJECT_ID('dbo.startup_scorecards_summary', 'U') IS NULL
BEGIN

    CREATE TABLE dbo.startup_scorecards_summary (
        scorecard_id       NVARCHAR(64)   NOT NULL,
        run_utc            NVARCHAR(32)   NOT NULL,
        run_end_utc        NVARCHAR(32)   NULL,
        runtime_label      NVARCHAR(64)   NULL,
        model_label        NVARCHAR(128)  NULL,
        graph_scan_success BIT            NOT NULL DEFAULT 0,
        emails_considered  INT            NULL,
        matched            INT            NULL,
        unmatched          INT            NULL,
        same_day_count     INT            NULL,
        high_count         INT            NULL,
        normal_count       INT            NULL,
        low_count          INT            NULL,
        sub_results_json   NVARCHAR(1000) NULL,
        inserted_utc       DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_startup_scorecards_summary PRIMARY KEY (scorecard_id)
    )
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.startup_scorecards_summary')
      AND name = 'IX_startup_scorecards_summary_run_utc'
)
    CREATE INDEX IX_startup_scorecards_summary_run_utc
        ON dbo.startup_scorecards_summary (run_utc DESC)
GO


CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE IF NOT EXISTS telemetry.runtime_activation_events (
    event_id         TEXT        NOT NULL PRIMARY KEY,
    event             TEXT        NOT NULL,
    run_utc           TEXT        NOT NULL,
    run_end_utc       TEXT,
    runtime_label     TEXT,
    model_label       TEXT,
    command           TEXT,
    sub_results_json  TEXT,
    inserted_utc      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_telemetry_runtime_activation_events_run_utc
    ON telemetry.runtime_activation_events (run_utc DESC);

CREATE TABLE IF NOT EXISTS telemetry.runtime_event_hourly (
    hour_utc         TEXT        NOT NULL,
    runtime_label    TEXT        NOT NULL,
    event_name       TEXT        NOT NULL,
    events           INTEGER     NOT NULL DEFAULT 0,
    errors           INTEGER     NOT NULL DEFAULT 0,
    first_timestamp  TEXT,
    last_timestamp   TEXT,
    updated_utc      TEXT,
    inserted_utc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (hour_utc, runtime_label, event_name)
);
CREATE INDEX IF NOT EXISTS ix_telemetry_runtime_event_hourly_updated_utc
    ON telemetry.runtime_event_hourly (updated_utc DESC);

CREATE TABLE IF NOT EXISTS telemetry.startup_scorecards_summary (
    scorecard_id        TEXT        NOT NULL PRIMARY KEY,
    run_utc             TEXT        NOT NULL,
    run_end_utc         TEXT,
    runtime_label       TEXT,
    model_label         TEXT,
    graph_scan_success  SMALLINT    NOT NULL DEFAULT 0,
    emails_considered   INTEGER,
    matched             INTEGER,
    unmatched           INTEGER,
    same_day_count      INTEGER,
    high_count          INTEGER,
    normal_count        INTEGER,
    low_count           INTEGER,
    sub_results_json    TEXT,
    inserted_utc        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_telemetry_startup_scorecards_summary_run_utc
    ON telemetry.startup_scorecards_summary (run_utc DESC);

CREATE TABLE IF NOT EXISTS telemetry.session_events (
    event_key     TEXT NOT NULL PRIMARY KEY,
    timestamp     TEXT NOT NULL,
    model_label   TEXT,
    tool_name     TEXT NOT NULL,
    target        TEXT,
    session_id    TEXT,
    inserted_utc  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_telemetry_session_events_timestamp
    ON telemetry.session_events (timestamp);
CREATE INDEX IF NOT EXISTS ix_telemetry_session_events_session
    ON telemetry.session_events (session_id);

CREATE TABLE IF NOT EXISTS telemetry.graph_api_calls_daily (
    day_utc          TEXT        NOT NULL,
    call_type        TEXT        NOT NULL,
    total_calls      INTEGER     NOT NULL DEFAULT 0,
    success_count    INTEGER     NOT NULL DEFAULT 0,
    error_count      INTEGER     NOT NULL DEFAULT 0,
    avg_duration_ms  INTEGER,
    runtime_label    TEXT,
    inserted_utc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day_utc, call_type)
);

CREATE TABLE IF NOT EXISTS telemetry.client_search_events (
    event_id          TEXT        NOT NULL PRIMARY KEY,
    recorded_at       TEXT        NOT NULL,
    query_kind        TEXT,
    resolver_success  SMALLINT    NOT NULL DEFAULT 0,
    confidence_hint   TEXT,
    is_typo           SMALLINT    NOT NULL DEFAULT 0,
    runtime_label     TEXT,
    inserted_utc      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_telemetry_client_search_events_recorded_at
    ON telemetry.client_search_events (recorded_at);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'telemetry_writer') THEN
        CREATE ROLE telemetry_writer NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA telemetry TO telemetry_writer;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA telemetry TO telemetry_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA telemetry
    GRANT SELECT, INSERT, UPDATE ON TABLES TO telemetry_writer;

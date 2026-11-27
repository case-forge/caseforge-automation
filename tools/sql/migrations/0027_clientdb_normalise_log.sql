
CREATE TABLE IF NOT EXISTS clientdb_normalise_log (
    log_id       BIGSERIAL   PRIMARY KEY,
    run_tag      TEXT        NOT NULL,
    table_name   TEXT        NOT NULL,
    pk_column    TEXT        NOT NULL,
    pk_value     TEXT        NOT NULL,
    column_name  TEXT        NOT NULL,
    old_value    TEXT        NULL,
    new_value    TEXT        NULL,
    applied_utc  TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc'),
    reverted_utc TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_clientdb_normalise_log_run ON clientdb_normalise_log(run_tag);

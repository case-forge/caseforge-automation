
CREATE TABLE IF NOT EXISTS client_todos (
    todo_id       TEXT    PRIMARY KEY,
    title         TEXT    NOT NULL,
    notes         TEXT    NOT NULL DEFAULT '',
    matter_id     INTEGER NULL,
    assignee      TEXT    NOT NULL DEFAULT '',
    created_by    TEXT    NOT NULL DEFAULT '',
    due_utc       TEXT    NULL,
    due_has_time  INTEGER NOT NULL DEFAULT 0,
    starred       INTEGER NOT NULL DEFAULT 0,
    my_day_date   TEXT    NULL,
    source        TEXT    NOT NULL DEFAULT 'manual',
    source_ref    TEXT    NOT NULL DEFAULT '',
    created_utc   TEXT    NOT NULL,
    updated_utc   TEXT    NOT NULL,
    done_utc      TEXT    NULL,
    done_by       TEXT    NOT NULL DEFAULT '',
    deleted_utc   TEXT    NULL
);

CREATE INDEX IF NOT EXISTS ix_client_todos_open ON client_todos (done_utc, deleted_utc, due_utc);
CREATE INDEX IF NOT EXISTS ix_client_todos_matter ON client_todos (matter_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_client_todos_source ON client_todos (source, source_ref) WHERE source_ref <> '';

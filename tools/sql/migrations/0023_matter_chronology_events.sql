
CREATE TABLE IF NOT EXISTS matter_chronology_events (
    event_id             SERIAL  PRIMARY KEY,
    matter_id             INTEGER NOT NULL REFERENCES matters (matter_id) ON DELETE CASCADE,
    event_date            TEXT    NULL,
    event_time            TEXT    NULL,
    event_type            TEXT    NULL,
    hearing_type          TEXT    NULL,
    on_notice             BOOLEAN NULL,
    event_text            TEXT    NULL,
    outcome               TEXT    NULL,
    source_label          TEXT    NULL,
    source_path_or_item_id TEXT   NULL,
    court_facing          BOOLEAN NULL,
    include_in_bundle     BOOLEAN NULL,
    confidence            TEXT    NULL,
    created_utc           TEXT    NULL,
    updated_utc           TEXT    NULL
);

CREATE INDEX IF NOT EXISTS ix_matter_chronology_events_matter_id ON matter_chronology_events (matter_id);

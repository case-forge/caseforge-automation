
CREATE TABLE IF NOT EXISTS matter_incidents (
    incident_id      SERIAL  PRIMARY KEY,
    matter_id        INTEGER NOT NULL REFERENCES matters (matter_id) ON DELETE CASCADE,
    incident_date    TEXT    NULL,
    incident_type    TEXT    NULL,
    summary          TEXT    NULL,
    police_called    BOOLEAN NULL,
    crime_reference  TEXT    NULL,
    arrest_status    TEXT    NULL,
    bail_status      TEXT    NULL,
    source_label     TEXT    NULL,
    source_date      TEXT    NULL,
    confidence       TEXT    NULL,
    created_utc      TEXT    NULL,
    updated_utc      TEXT    NULL
);

CREATE INDEX IF NOT EXISTS ix_matter_incidents_matter_id ON matter_incidents (matter_id);

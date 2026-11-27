
CREATE TABLE IF NOT EXISTS matter_orders (
    order_id         SERIAL  PRIMARY KEY,
    matter_id        INTEGER NOT NULL REFERENCES matters (matter_id) ON DELETE CASCADE,
    order_type       TEXT    NULL,
    status           TEXT    NULL,
    requested_date   TEXT    NULL,
    made_date        TEXT    NULL,
    expiry_date      TEXT    NULL,
    court            TEXT    NULL,
    case_number      TEXT    NULL,
    notes            TEXT    NULL,
    source           TEXT    NULL,
    created_utc      TEXT    NULL,
    updated_utc      TEXT    NULL
);

CREATE INDEX IF NOT EXISTS ix_matter_orders_matter ON matter_orders (matter_id);
CREATE INDEX IF NOT EXISTS ix_matter_orders_type ON matter_orders (matter_id, order_type);

SELECT clientdb_change_log_attach_table('matter_orders');

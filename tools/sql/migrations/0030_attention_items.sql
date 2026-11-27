
CREATE TABLE IF NOT EXISTS attention_items (
    item_id           TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,
    matter_id         TEXT NOT NULL DEFAULT '',
    who               TEXT NOT NULL DEFAULT '',
    subject           TEXT NOT NULL DEFAULT '',
    summary           TEXT NOT NULL DEFAULT '',
    deadline          TEXT NOT NULL DEFAULT '',
    importance        TEXT NOT NULL DEFAULT 'normal',
    label             TEXT NOT NULL DEFAULT '',
    complaint_domain  TEXT NOT NULL DEFAULT '',
    settlement_stage  TEXT NOT NULL DEFAULT '',
    sender_domain     TEXT NOT NULL DEFAULT '',
    web_link          TEXT NOT NULL DEFAULT '',
    message_key       TEXT NOT NULL,
    created_utc       TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'open',
    done_by           TEXT NOT NULL DEFAULT '',
    done_utc          TEXT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_attention_items_message ON attention_items (message_key);
CREATE INDEX IF NOT EXISTS ix_attention_items_open ON attention_items (status, kind, created_utc);
CREATE INDEX IF NOT EXISTS ix_attention_items_matter ON attention_items (matter_id);

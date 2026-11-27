
CREATE TABLE IF NOT EXISTS clientdb_change_log (
    id              BIGSERIAL   PRIMARY KEY,
    at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    table_name      TEXT        NOT NULL,
    op              TEXT        NOT NULL CHECK (op IN ('INSERT', 'UPDATE', 'DELETE')),
    pk              JSONB       NULL,
    old_row         JSONB       NULL,
    new_row         JSONB       NULL,
    changed_columns TEXT[]      NULL,
    actor           TEXT        NULL,
    app             TEXT        NULL,
    txid            BIGINT      NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_clientdb_change_log_table_at ON clientdb_change_log (table_name, at);
CREATE INDEX IF NOT EXISTS ix_clientdb_change_log_txid ON clientdb_change_log (txid);

CREATE OR REPLACE FUNCTION clientdb_change_log_capture()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    old_j   JSONB := NULL;
    new_j   JSONB := NULL;
    key_src JSONB;
    changed TEXT[] := NULL;
    pk_j    JSONB := NULL;
    n       INTEGER;
    who     TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        new_j := to_jsonb(NEW);
        key_src := new_j;
    ELSIF TG_OP = 'DELETE' THEN
        old_j := to_jsonb(OLD);
        key_src := old_j;
    ELSE
        old_j := to_jsonb(OLD);
        new_j := to_jsonb(NEW);
        IF old_j = new_j THEN
            RETURN NULL;
        END IF;
        SELECT array_agg(c.key ORDER BY c.key) INTO changed
        FROM jsonb_each(new_j) AS c
        WHERE c.value IS DISTINCT FROM (old_j -> c.key);

        key_src := old_j;
    END IF;

    IF TG_NARGS > 0 THEN
        pk_j := '{}'::jsonb;
        FOR n IN 0 .. TG_NARGS - 1 LOOP

            pk_j := pk_j || jsonb_build_object(TG_ARGV[0 + n], key_src -> TG_ARGV[0 + n]);
        END LOOP;
    END IF;

    who := NULLIF(current_setting('caseforge.actor', true), '');
    IF who IS NULL THEN
        who := 'db:' || session_user;
    END IF;

    INSERT INTO clientdb_change_log (table_name, op, pk, old_row, new_row, changed_columns, actor, app, txid)
    VALUES (TG_TABLE_NAME, TG_OP, pk_j, old_j, new_j, changed, who,
            NULLIF(current_setting('application_name', true), ''), txid_current());
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION clientdb_change_log_refuse()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_TABLE_NAME = 'clientdb_change_log' THEN
        RAISE EXCEPTION 'clientdb_change_log is append-only';
    END IF;
    RAISE EXCEPTION 'TRUNCATE is refused on a change-logged table; DELETE the rows so each is logged';
END;
$$;

DROP TRIGGER IF EXISTS clientdb_change_log_append_only ON clientdb_change_log;
CREATE TRIGGER clientdb_change_log_append_only
    BEFORE UPDATE OR DELETE ON clientdb_change_log
    FOR EACH ROW EXECUTE FUNCTION clientdb_change_log_refuse();
DROP TRIGGER IF EXISTS clientdb_change_log_no_truncate ON clientdb_change_log;
CREATE TRIGGER clientdb_change_log_no_truncate
    BEFORE TRUNCATE ON clientdb_change_log
    FOR EACH STATEMENT EXECUTE FUNCTION clientdb_change_log_refuse();

CREATE OR REPLACE FUNCTION clientdb_change_log_attach_table(tbl TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    rel      REGCLASS := to_regclass(quote_ident(tbl));
    pk_args  TEXT;
BEGIN
    IF rel IS NULL OR tbl = 'clientdb_change_log' THEN
        RETURN false;
    END IF;
    SELECT string_agg(quote_literal(a.attname), ', ' ORDER BY k.ord) INTO pk_args
    FROM pg_index i
    CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
    WHERE i.indrelid = rel AND i.indisprimary;

    EXECUTE 'DROP TRIGGER IF EXISTS clientdb_change_log ON ' || rel::text;
    EXECUTE 'CREATE TRIGGER clientdb_change_log AFTER INSERT OR UPDATE OR DELETE ON '
        || rel::text || ' FOR EACH ROW EXECUTE FUNCTION clientdb_change_log_capture('
        || COALESCE(pk_args, '') || ')';
    EXECUTE 'DROP TRIGGER IF EXISTS clientdb_change_log_no_truncate ON ' || rel::text;
    EXECUTE 'CREATE TRIGGER clientdb_change_log_no_truncate BEFORE TRUNCATE ON '
        || rel::text || ' FOR EACH STATEMENT EXECUTE FUNCTION clientdb_change_log_refuse()';
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION clientdb_change_log_attach()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    covered  TEXT[] := ARRAY[
        'people', 'person_aliases', 'matters', 'matter_parties', 'matter_references',
        'matter_children', 'matter_bank_details', 'matter_permissions',
        'matter_folder_locations', 'matter_incidents', 'matter_chronology_events',
        'matter_hearings', 'matter_hearing_events', 'matter_hearing_leads',
        'client_todos', 'attention_items'
    ];
    excluded TEXT[] := ARRAY[
        'matter_live_status'
    ];
    t        TEXT;
    attached INTEGER := 0;
BEGIN
    FOR t IN
        SELECT DISTINCT name FROM (
            SELECT unnest(covered) AS name
            UNION
            SELECT c.relname::text
            FROM pg_class c
            WHERE c.relnamespace = current_schema()::regnamespace
              AND c.relkind IN ('r', 'p')
              AND starts_with(c.relname::text, 'matter_')
        ) names
        WHERE NOT (name = ANY (excluded))
        ORDER BY name
    LOOP
        IF clientdb_change_log_attach_table(t) THEN
            attached := attached + 1;
        END IF;
    END LOOP;
    RETURN attached;
END;
$$;

SELECT clientdb_change_log_attach();

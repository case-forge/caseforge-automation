
ALTER TABLE matter_children
    ADD COLUMN IF NOT EXISTS client_person_id INTEGER NULL
        REFERENCES people (person_id) ON DELETE SET NULL;
ALTER TABLE matter_children
    ADD COLUMN IF NOT EXISTS respondent_party_id INTEGER NULL
        REFERENCES matter_parties (matter_party_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_matter_children_client_person ON matter_children (client_person_id);
CREATE INDEX IF NOT EXISTS ix_matter_children_respondent_party ON matter_children (respondent_party_id);

SELECT clientdb_change_log_attach_table('matter_children');

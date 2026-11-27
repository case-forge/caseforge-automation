
CREATE INDEX IF NOT EXISTS ix_people_email_primary_lower
    ON people (lower(trim(email_primary)));
CREATE INDEX IF NOT EXISTS ix_people_email_primary_dotless
    ON people (replace(lower(trim(email_primary)), '.', ''));
CREATE INDEX IF NOT EXISTS ix_matter_parties_email_primary_lower
    ON matter_parties (lower(trim(email_primary)));
CREATE INDEX IF NOT EXISTS ix_matter_parties_email_primary_dotless
    ON matter_parties (replace(lower(trim(email_primary)), '.', ''));


ALTER TABLE matter_parties ADD COLUMN IF NOT EXISTS address_owner TEXT NULL;
ALTER TABLE matter_parties ADD COLUMN IF NOT EXISTS phone_owner TEXT NULL;
ALTER TABLE matter_parties ADD COLUMN IF NOT EXISTS email_owner TEXT NULL;

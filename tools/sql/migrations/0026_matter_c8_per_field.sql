
ALTER TABLE matters ADD COLUMN IF NOT EXISTS c8_phone integer NOT NULL DEFAULT 0;
ALTER TABLE matters ADD COLUMN IF NOT EXISTS c8_email integer NOT NULL DEFAULT 0;
ALTER TABLE matters ADD COLUMN IF NOT EXISTS c8_address integer NOT NULL DEFAULT 0;

UPDATE matters
   SET c8_phone = 1, c8_email = 1, c8_address = 1
 WHERE has_c8 <> 0 AND c8_phone = 0 AND c8_email = 0 AND c8_address = 0;


IF OBJECT_ID(N'dbo.matter_bank_details', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.matter_bank_details (
        bank_detail_id   INT IDENTITY(1,1)  NOT NULL,
        matter_id        INT                NOT NULL,
        account_name     NVARCHAR(300)      NULL,
        account_number   NVARCHAR(50)       NULL,
        sort_code        NVARCHAR(20)       NULL,
        amount           NVARCHAR(50)       NULL,
        notes            NVARCHAR(MAX)      NULL,
        source           NVARCHAR(100)      NULL,
        created_utc      DATETIME2          NULL,
        updated_utc      DATETIME2          NULL,

        CONSTRAINT pk_matter_bank_details PRIMARY KEY (bank_detail_id),
        CONSTRAINT fk_matter_bank_details_matter
            FOREIGN KEY (matter_id) REFERENCES dbo.matters (matter_id)
            ON DELETE CASCADE
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_matter_bank_details_matter_id'
      AND object_id = OBJECT_ID('dbo.matter_bank_details')
)
BEGIN
    CREATE INDEX ix_matter_bank_details_matter_id
    ON dbo.matter_bank_details (matter_id);
END;
GO

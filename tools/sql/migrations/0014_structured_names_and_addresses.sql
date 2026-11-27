
IF COL_LENGTH('dbo.people', 'name_first') IS NULL
    ALTER TABLE dbo.people ADD name_first NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.people', 'name_middle') IS NULL
    ALTER TABLE dbo.people ADD name_middle NVARCHAR(150) NULL;
GO
IF COL_LENGTH('dbo.people', 'name_last') IS NULL
    ALTER TABLE dbo.people ADD name_last NVARCHAR(150) NULL;
GO

IF COL_LENGTH('dbo.people', 'address_text') IS NULL
    ALTER TABLE dbo.people ADD address_text NVARCHAR(MAX) NULL;
GO
IF COL_LENGTH('dbo.people', 'address_line1') IS NULL
    ALTER TABLE dbo.people ADD address_line1 NVARCHAR(255) NULL;
GO
IF COL_LENGTH('dbo.people', 'address_line2') IS NULL
    ALTER TABLE dbo.people ADD address_line2 NVARCHAR(255) NULL;
GO
IF COL_LENGTH('dbo.people', 'address_line3') IS NULL
    ALTER TABLE dbo.people ADD address_line3 NVARCHAR(255) NULL;
GO
IF COL_LENGTH('dbo.people', 'address_line4') IS NULL
    ALTER TABLE dbo.people ADD address_line4 NVARCHAR(255) NULL;
GO

IF COL_LENGTH('dbo.people', 'address_postcode') IS NULL
    ALTER TABLE dbo.people ADD address_postcode NVARCHAR(16) NULL;
GO

IF COL_LENGTH('dbo.matter_parties', 'name_first') IS NULL
    ALTER TABLE dbo.matter_parties ADD name_first NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.matter_parties', 'name_middle') IS NULL
    ALTER TABLE dbo.matter_parties ADD name_middle NVARCHAR(150) NULL;
GO
IF COL_LENGTH('dbo.matter_parties', 'name_last') IS NULL
    ALTER TABLE dbo.matter_parties ADD name_last NVARCHAR(150) NULL;
GO
IF COL_LENGTH('dbo.matter_parties', 'address_line1') IS NULL
    ALTER TABLE dbo.matter_parties ADD address_line1 NVARCHAR(255) NULL;
GO
IF COL_LENGTH('dbo.matter_parties', 'address_line2') IS NULL
    ALTER TABLE dbo.matter_parties ADD address_line2 NVARCHAR(255) NULL;
GO
IF COL_LENGTH('dbo.matter_parties', 'address_line3') IS NULL
    ALTER TABLE dbo.matter_parties ADD address_line3 NVARCHAR(255) NULL;
GO
IF COL_LENGTH('dbo.matter_parties', 'address_line4') IS NULL
    ALTER TABLE dbo.matter_parties ADD address_line4 NVARCHAR(255) NULL;
GO
IF COL_LENGTH('dbo.matter_parties', 'address_postcode') IS NULL
    ALTER TABLE dbo.matter_parties ADD address_postcode NVARCHAR(16) NULL;
GO

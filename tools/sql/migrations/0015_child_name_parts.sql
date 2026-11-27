
IF COL_LENGTH('dbo.matter_children', 'name_first') IS NULL
    ALTER TABLE dbo.matter_children ADD name_first NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.matter_children', 'name_middle') IS NULL
    ALTER TABLE dbo.matter_children ADD name_middle NVARCHAR(150) NULL;
GO
IF COL_LENGTH('dbo.matter_children', 'name_last') IS NULL
    ALTER TABLE dbo.matter_children ADD name_last NVARCHAR(150) NULL;
GO

IF OBJECT_ID(N'dbo.APP_LeadsDirectOS', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_LeadsDirectOS
    (
        LeadId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_APP_LeadsDirectOS PRIMARY KEY,
        Nome NVARCHAR(150) NOT NULL,
        Empresa NVARCHAR(150) NULL,
        Email NVARCHAR(150) NULL,
        Whatsapp NVARCHAR(50) NULL,
        TipoNegocio NVARCHAR(150) NULL,
        VolumeOSMes NVARCHAR(50) NULL,
        Mensagem NVARCHAR(MAX) NULL,
        Origem NVARCHAR(100) NULL,
        UtmSource NVARCHAR(100) NULL,
        UtmMedium NVARCHAR(100) NULL,
        UtmCampaign NVARCHAR(100) NULL,
        DataCadastro DATETIME2 NOT NULL CONSTRAINT DF_APP_LeadsDirectOS_DataCadastro DEFAULT SYSDATETIME(),
        Status NVARCHAR(50) NOT NULL CONSTRAINT DF_APP_LeadsDirectOS_Status DEFAULT N'Novo'
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_APP_LeadsDirectOS_DataCadastro'
      AND object_id = OBJECT_ID(N'dbo.APP_LeadsDirectOS')
)
BEGIN
    CREATE INDEX IX_APP_LeadsDirectOS_DataCadastro
        ON dbo.APP_LeadsDirectOS (DataCadastro DESC);
END;
GO

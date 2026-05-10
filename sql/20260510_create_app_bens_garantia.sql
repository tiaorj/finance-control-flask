IF OBJECT_ID('dbo.APP_BensGarantia', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_BensGarantia (
        BemId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        Nome NVARCHAR(140) NOT NULL,
        Categoria NVARCHAR(80) NULL,
        Marca NVARCHAR(80) NULL,
        Modelo NVARCHAR(100) NULL,
        DataCompra DATE NOT NULL,
        MesesGarantia INT NOT NULL,
        ValorCompra DECIMAL(12,2) NULL,
        LocalCompra NVARCHAR(140) NULL,
        NotaFiscalUrl NVARCHAR(500) NULL,
        NotaFiscalArquivo NVARCHAR(255) NULL,
        Ativo BIT NOT NULL DEFAULT 1,
        Observacoes NVARCHAR(500) NULL,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_APP_BensGarantia_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT CK_APP_BensGarantia_Meses
            CHECK (MesesGarantia >= 0)
    );
END;

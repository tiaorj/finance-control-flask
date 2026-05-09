IF OBJECT_ID('dbo.FIN_Assinaturas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FIN_Assinaturas (
        AssinaturaId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        Nome NVARCHAR(120) NOT NULL,
        Categoria NVARCHAR(80) NULL,
        Valor DECIMAL(12,2) NOT NULL,
        Ciclo NVARCHAR(20) NOT NULL,
        DataRenovacao DATE NOT NULL,
        Ativa BIT NOT NULL DEFAULT 1,
        Observacoes NVARCHAR(500) NULL,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_FIN_Assinaturas_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT CK_FIN_Assinaturas_Ciclo
            CHECK (Ciclo IN ('mensal', 'anual'))
    );
END;

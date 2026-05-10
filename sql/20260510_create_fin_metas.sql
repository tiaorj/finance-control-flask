IF OBJECT_ID('dbo.FIN_Metas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FIN_Metas (
        MetaId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        Nome NVARCHAR(120) NOT NULL,
        ValorAlvo DECIMAL(12,2) NOT NULL,
        ValorAtual DECIMAL(12,2) NOT NULL DEFAULT 0,
        DataAlvo DATE NULL,
        CorHex NVARCHAR(20) NULL,
        Ativa BIT NOT NULL DEFAULT 1,
        Observacoes NVARCHAR(500) NULL,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_FIN_Metas_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId)
    );
END;

IF OBJECT_ID('dbo.FIN_MetaMovimentacoes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FIN_MetaMovimentacoes (
        MovimentacaoId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        MetaId INT NOT NULL,
        UsuarioId INT NOT NULL,
        Tipo NVARCHAR(20) NOT NULL,
        Valor DECIMAL(12,2) NOT NULL,
        Observacao NVARCHAR(300) NULL,
        DataMovimentacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_FIN_MetaMovimentacoes_Metas
            FOREIGN KEY (MetaId) REFERENCES dbo.FIN_Metas(MetaId),
        CONSTRAINT FK_FIN_MetaMovimentacoes_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT CK_FIN_MetaMovimentacoes_Tipo
            CHECK (Tipo IN ('aporte', 'retirada'))
    );
END;

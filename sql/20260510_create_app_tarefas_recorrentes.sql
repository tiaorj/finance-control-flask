IF OBJECT_ID('dbo.APP_TarefasRecorrentes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_TarefasRecorrentes (
        TarefaId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        Titulo NVARCHAR(140) NOT NULL,
        Categoria NVARCHAR(80) NULL,
        Periodicidade NVARCHAR(20) NOT NULL,
        IntervaloMeses INT NOT NULL DEFAULT 1,
        ProximaData DATE NOT NULL,
        UltimaConclusao DATETIME2 NULL,
        Ativa BIT NOT NULL DEFAULT 1,
        Observacoes NVARCHAR(500) NULL,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_APP_TarefasRecorrentes_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT CK_APP_TarefasRecorrentes_Periodicidade
            CHECK (Periodicidade IN ('mensal', 'bimestral', 'trimestral', 'semestral', 'anual', 'personalizado')),
        CONSTRAINT CK_APP_TarefasRecorrentes_Intervalo
            CHECK (IntervaloMeses > 0)
    );
END;

IF OBJECT_ID('dbo.APP_TarefaConclusoes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_TarefaConclusoes (
        ConclusaoId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        TarefaId INT NOT NULL,
        UsuarioId INT NOT NULL,
        DataConclusao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        ProximaDataGerada DATE NULL,
        Observacao NVARCHAR(300) NULL,
        CONSTRAINT FK_APP_TarefaConclusoes_Tarefas
            FOREIGN KEY (TarefaId) REFERENCES dbo.APP_TarefasRecorrentes(TarefaId),
        CONSTRAINT FK_APP_TarefaConclusoes_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId)
    );
END;

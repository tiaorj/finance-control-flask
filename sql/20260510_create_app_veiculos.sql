IF OBJECT_ID('dbo.APP_Veiculos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_Veiculos (
        VeiculoId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        Apelido NVARCHAR(100) NOT NULL,
        Tipo NVARCHAR(20) NOT NULL,
        Marca NVARCHAR(80) NULL,
        Modelo NVARCHAR(100) NULL,
        Ano INT NULL,
        Placa NVARCHAR(20) NULL,
        QuilometragemAtual INT NULL,
        Ativo BIT NOT NULL DEFAULT 1,
        Observacoes NVARCHAR(500) NULL,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_APP_Veiculos_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT CK_APP_Veiculos_Tipo
            CHECK (Tipo IN ('carro', 'moto', 'utilitario', 'outro'))
    );
END;

IF OBJECT_ID('dbo.APP_VeiculoLembretes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_VeiculoLembretes (
        LembreteId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        VeiculoId INT NOT NULL,
        UsuarioId INT NOT NULL,
        Tipo NVARCHAR(30) NOT NULL,
        Titulo NVARCHAR(140) NOT NULL,
        DataVencimento DATE NULL,
        KmVencimento INT NULL,
        RecorrenciaMeses INT NULL,
        IntervaloKm INT NULL,
        ValorEstimado DECIMAL(12,2) NULL,
        Concluido BIT NOT NULL DEFAULT 0,
        UltimaConclusao DATETIME2 NULL,
        Observacoes NVARCHAR(500) NULL,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_APP_VeiculoLembretes_Veiculos
            FOREIGN KEY (VeiculoId) REFERENCES dbo.APP_Veiculos(VeiculoId),
        CONSTRAINT FK_APP_VeiculoLembretes_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT CK_APP_VeiculoLembretes_Tipo
            CHECK (Tipo IN ('oleo', 'ipva', 'seguro', 'pneus', 'licenciamento', 'revisao', 'outro'))
    );
END;

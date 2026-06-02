IF OBJECT_ID('dbo.FIN_LancamentosRecorrentes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FIN_LancamentosRecorrentes (
        LancamentoRecorrenteId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        CategoriaId INT NOT NULL,
        Descricao NVARCHAR(140) NOT NULL,
        ValorEstimado DECIMAL(18,2) NOT NULL DEFAULT 0,
        DiaVencimento INT NOT NULL,
        Periodicidade NVARCHAR(20) NOT NULL DEFAULT 'mensal',
        IntervaloMeses INT NOT NULL DEFAULT 1,
        DataInicio DATE NOT NULL,
        DataFim DATE NULL,
        ParcelaInicial INT NULL,
        ParcelaTotal INT NULL,
        Ativa BIT NOT NULL DEFAULT 1,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_FIN_LancamentosRecorrentes_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT CK_FIN_LancamentosRecorrentes_Dia
            CHECK (DiaVencimento BETWEEN 1 AND 31),
        CONSTRAINT CK_FIN_LancamentosRecorrentes_Intervalo
            CHECK (IntervaloMeses > 0),
        CONSTRAINT CK_FIN_LancamentosRecorrentes_Periodicidade
            CHECK (Periodicidade IN ('mensal', 'bimestral', 'trimestral', 'semestral', 'anual', 'personalizado'))
    );
END;

IF OBJECT_ID('dbo.FIN_LancamentoRecorrenteOcorrencias', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FIN_LancamentoRecorrenteOcorrencias (
        OcorrenciaId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        LancamentoRecorrenteId INT NOT NULL,
        LancamentoId INT NOT NULL,
        MesReferencia INT NOT NULL,
        AnoReferencia INT NOT NULL,
        Ignorado BIT NOT NULL DEFAULT 0,
        DataSincronizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_FIN_LancamentoRecorrenteOcorrencias_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT FK_FIN_LancamentoRecorrenteOcorrencias_Recorrentes
            FOREIGN KEY (LancamentoRecorrenteId) REFERENCES dbo.FIN_LancamentosRecorrentes(LancamentoRecorrenteId)
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_FIN_LancamentoRecorrenteOcorrencias_Periodo'
      AND object_id = OBJECT_ID('dbo.FIN_LancamentoRecorrenteOcorrencias')
)
BEGIN
    CREATE UNIQUE INDEX UX_FIN_LancamentoRecorrenteOcorrencias_Periodo
    ON dbo.FIN_LancamentoRecorrenteOcorrencias (UsuarioId, LancamentoRecorrenteId, MesReferencia, AnoReferencia);
END;

IF COL_LENGTH('dbo.FIN_LancamentoRecorrenteOcorrencias', 'Ignorado') IS NULL
BEGIN
    ALTER TABLE dbo.FIN_LancamentoRecorrenteOcorrencias
    ADD Ignorado BIT NOT NULL
        CONSTRAINT DF_FIN_LancamentoRecorrenteOcorrencias_Ignorado DEFAULT 0;
END;

IF COL_LENGTH('dbo.FIN_Lancamentos', 'LancamentoRecorrenteId') IS NULL
BEGIN
    ALTER TABLE dbo.FIN_Lancamentos ADD LancamentoRecorrenteId INT NULL;
END;

IF COL_LENGTH('dbo.FIN_Lancamentos', 'ParcelaNumero') IS NULL
BEGIN
    ALTER TABLE dbo.FIN_Lancamentos ADD ParcelaNumero INT NULL;
END;

IF COL_LENGTH('dbo.FIN_Lancamentos', 'ParcelaTotal') IS NULL
BEGIN
    ALTER TABLE dbo.FIN_Lancamentos ADD ParcelaTotal INT NULL;
END;

IF COL_LENGTH('dbo.FIN_LancamentosRecorrentes', 'ParcelaInicial') IS NULL
BEGIN
    ALTER TABLE dbo.FIN_LancamentosRecorrentes ADD ParcelaInicial INT NULL;
END;

IF COL_LENGTH('dbo.FIN_LancamentosRecorrentes', 'ParcelaTotal') IS NULL
BEGIN
    ALTER TABLE dbo.FIN_LancamentosRecorrentes ADD ParcelaTotal INT NULL;
END;

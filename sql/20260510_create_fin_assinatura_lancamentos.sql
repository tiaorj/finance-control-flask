IF OBJECT_ID('dbo.FIN_AssinaturaLancamentos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FIN_AssinaturaLancamentos (
        AssinaturaLancamentoId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        AssinaturaId INT NOT NULL,
        LancamentoId INT NOT NULL,
        MesReferencia INT NOT NULL,
        AnoReferencia INT NOT NULL,
        Ignorado BIT NOT NULL DEFAULT 0,
        DataSincronizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_FIN_AssinaturaLancamentos_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT FK_FIN_AssinaturaLancamentos_Assinaturas
            FOREIGN KEY (AssinaturaId) REFERENCES dbo.FIN_Assinaturas(AssinaturaId)
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_FIN_AssinaturaLancamentos_Periodo'
      AND object_id = OBJECT_ID('dbo.FIN_AssinaturaLancamentos')
)
BEGIN
    CREATE UNIQUE INDEX UX_FIN_AssinaturaLancamentos_Periodo
    ON dbo.FIN_AssinaturaLancamentos (UsuarioId, AssinaturaId, MesReferencia, AnoReferencia);
END;

IF COL_LENGTH('dbo.FIN_AssinaturaLancamentos', 'Ignorado') IS NULL
BEGIN
    ALTER TABLE dbo.FIN_AssinaturaLancamentos
    ADD Ignorado BIT NOT NULL
        CONSTRAINT DF_FIN_AssinaturaLancamentos_Ignorado DEFAULT 0;
END;

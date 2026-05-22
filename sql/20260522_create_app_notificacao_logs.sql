IF OBJECT_ID('dbo.APP_NotificacaoLogs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_NotificacaoLogs (
        NotificacaoLogId INT IDENTITY(1,1) NOT NULL,
        UsuarioId INT NOT NULL,
        Tipo VARCHAR(50) NOT NULL,
        EmailDestino VARCHAR(255) NULL,
        Assunto VARCHAR(255) NOT NULL,
        Status VARCHAR(30) NOT NULL,
        MensagemErro VARCHAR(MAX) NULL,
        DataEnvio DATETIME2 NOT NULL CONSTRAINT DF_APP_NotificacaoLogs_DataEnvio DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_APP_NotificacaoLogs PRIMARY KEY (NotificacaoLogId),
        CONSTRAINT FK_APP_NotificacaoLogs_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId)
    );
END;

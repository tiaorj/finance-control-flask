IF OBJECT_ID('dbo.CurriculoPerfil', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CurriculoPerfil (
        CurriculoPerfilId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL UNIQUE,
        NomeExibicao NVARCHAR(150) NOT NULL,
        Cargo NVARCHAR(200) NULL,
        Resumo NVARCHAR(MAX) NULL,
        Localizacao NVARCHAR(150) NULL,
        Telefone NVARCHAR(50) NULL,
        Email NVARCHAR(150) NULL,
        Linkedin NVARCHAR(250) NULL,
        FotoArquivo NVARCHAR(255) NULL,
        DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_CurriculoPerfil_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId)
    );
END;

INSERT INTO dbo.CurriculoPerfil (UsuarioId, NomeExibicao)
SELECT U.UsuarioId, U.Nome
FROM dbo.Usuarios U
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.CurriculoPerfil P
    WHERE P.UsuarioId = U.UsuarioId
);

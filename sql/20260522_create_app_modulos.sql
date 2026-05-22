IF OBJECT_ID('dbo.APP_Modulos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_Modulos (
        ModuloId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Codigo VARCHAR(50) NOT NULL UNIQUE,
        Nome VARCHAR(100) NOT NULL,
        Descricao VARCHAR(255) NULL,
        Ativo BIT NOT NULL DEFAULT 1,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF OBJECT_ID('dbo.APP_UsuarioModulos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_UsuarioModulos (
        UsuarioModuloId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UsuarioId INT NOT NULL,
        ModuloId INT NOT NULL,
        Ativo BIT NOT NULL DEFAULT 1,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_APP_UsuarioModulos_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
        CONSTRAINT FK_APP_UsuarioModulos_Modulos
            FOREIGN KEY (ModuloId) REFERENCES dbo.APP_Modulos(ModuloId)
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_APP_UsuarioModulos_Usuario_Modulo'
      AND object_id = OBJECT_ID('dbo.APP_UsuarioModulos')
)
BEGIN
    CREATE UNIQUE INDEX UX_APP_UsuarioModulos_Usuario_Modulo
    ON dbo.APP_UsuarioModulos (UsuarioId, ModuloId);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.APP_Modulos WHERE Codigo = 'finance')
BEGIN
    INSERT INTO dbo.APP_Modulos (Codigo, Nome, Descricao)
    VALUES ('finance', 'DirectTI Finance', 'Controle financeiro pessoal e recorrencias.');
END;

IF NOT EXISTS (SELECT 1 FROM dbo.APP_Modulos WHERE Codigo = 'life')
BEGIN
    INSERT INTO dbo.APP_Modulos (Codigo, Nome, Descricao)
    VALUES ('life', 'DirectTI Life', 'Rotina, tarefas, veiculos, garantias e organizacao pessoal.');
END;

IF NOT EXISTS (SELECT 1 FROM dbo.APP_Modulos WHERE Codigo = 'careers')
BEGIN
    INSERT INTO dbo.APP_Modulos (Codigo, Nome, Descricao)
    VALUES ('careers', 'DirectTI Careers', 'Curriculo, perfil profissional e carreira.');
END;

INSERT INTO dbo.APP_UsuarioModulos (UsuarioId, ModuloId)
SELECT U.UsuarioId, M.ModuloId
FROM dbo.Usuarios U
CROSS JOIN dbo.APP_Modulos M
WHERE M.Codigo IN ('finance', 'life', 'careers')
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.APP_UsuarioModulos UM
      WHERE UM.UsuarioId = U.UsuarioId
        AND UM.ModuloId = M.ModuloId
  );

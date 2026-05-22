IF OBJECT_ID('dbo.APP_Workspaces', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_Workspaces (
        WorkspaceId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Nome VARCHAR(100) NOT NULL,
        Tipo VARCHAR(30) NOT NULL DEFAULT 'pessoal',
        DonoUsuarioId INT NOT NULL,
        Ativo BIT NOT NULL DEFAULT 1,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_APP_Workspaces_Usuarios
            FOREIGN KEY (DonoUsuarioId) REFERENCES dbo.Usuarios(UsuarioId)
    );
END;

IF OBJECT_ID('dbo.APP_WorkspaceUsuarios', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.APP_WorkspaceUsuarios (
        WorkspaceUsuarioId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        WorkspaceId INT NOT NULL,
        UsuarioId INT NOT NULL,
        NivelAcesso VARCHAR(30) NOT NULL DEFAULT 'dono',
        Ativo BIT NOT NULL DEFAULT 1,
        DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_APP_WorkspaceUsuarios_Workspaces
            FOREIGN KEY (WorkspaceId) REFERENCES dbo.APP_Workspaces(WorkspaceId),
        CONSTRAINT FK_APP_WorkspaceUsuarios_Usuarios
            FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId)
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_APP_Workspaces_Dono_TipoPessoal'
      AND object_id = OBJECT_ID('dbo.APP_Workspaces')
)
BEGIN
    CREATE UNIQUE INDEX UX_APP_Workspaces_Dono_TipoPessoal
    ON dbo.APP_Workspaces (DonoUsuarioId, Tipo)
    WHERE Tipo = 'pessoal';
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_APP_WorkspaceUsuarios_Workspace_Usuario'
      AND object_id = OBJECT_ID('dbo.APP_WorkspaceUsuarios')
)
BEGIN
    CREATE UNIQUE INDEX UX_APP_WorkspaceUsuarios_Workspace_Usuario
    ON dbo.APP_WorkspaceUsuarios (WorkspaceId, UsuarioId);
END;

INSERT INTO dbo.APP_Workspaces (Nome, Tipo, DonoUsuarioId)
SELECT LEFT(ISNULL(U.Nome, 'Workspace pessoal') + ' - Pessoal', 100), 'pessoal', U.UsuarioId
FROM dbo.Usuarios U
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.APP_Workspaces W
    WHERE W.DonoUsuarioId = U.UsuarioId
      AND W.Tipo = 'pessoal'
);

INSERT INTO dbo.APP_WorkspaceUsuarios (WorkspaceId, UsuarioId, NivelAcesso)
SELECT W.WorkspaceId, W.DonoUsuarioId, 'dono'
FROM dbo.APP_Workspaces W
WHERE W.Tipo = 'pessoal'
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.APP_WorkspaceUsuarios WU
      WHERE WU.WorkspaceId = W.WorkspaceId
        AND WU.UsuarioId = W.DonoUsuarioId
  );

SET XACT_ABORT ON;

IF OBJECT_ID('dbo.Usuarios', 'U') IS NULL
BEGIN
    THROW 50001, 'Tabela dbo.Usuarios nao encontrada.', 1;
END;

IF COL_LENGTH('dbo.Usuarios', 'IsAdmin') IS NULL
BEGIN
    ALTER TABLE dbo.Usuarios
    ADD IsAdmin BIT NOT NULL DEFAULT (0) WITH VALUES;
END;

IF COL_LENGTH('dbo.Usuarios', 'AdminTipo') IS NULL
BEGIN
    ALTER TABLE dbo.Usuarios
    ADD AdminTipo VARCHAR(30) NULL;
END;

-- Substitua pelo username/e-mail exato usado no login em dbo.Usuarios.Username.
DECLARE @AdminUsername VARCHAR(255) = 'SUBSTITUA_PELO_SEU_USERNAME';

IF @AdminUsername = 'SUBSTITUA_PELO_SEU_USERNAME'
BEGIN
    THROW 50002, 'Substitua @AdminUsername antes de executar este script.', 1;
END;

IF NOT EXISTS (SELECT 1 FROM dbo.Usuarios WHERE Username = @AdminUsername)
BEGIN
    THROW 50003, 'Usuario administrador nao encontrado em dbo.Usuarios.Username.', 1;
END;

BEGIN TRANSACTION;

    UPDATE dbo.Usuarios
    SET IsAdmin = 0,
        AdminTipo = NULL;

    UPDATE dbo.Usuarios
    SET IsAdmin = 1,
        AdminTipo = 'owner'
    WHERE Username = @AdminUsername;

COMMIT TRANSACTION;

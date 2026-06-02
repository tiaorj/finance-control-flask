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

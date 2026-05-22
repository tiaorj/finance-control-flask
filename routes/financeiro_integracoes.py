from calendar import monthrange
from datetime import date, datetime


def periodo_atual():
    hoje = datetime.now()
    return hoje.month, hoje.year


def chave_periodo(mes, ano):
    return ano * 12 + mes


def normalizar_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor:
        return datetime.strptime(valor[:10], '%Y-%m-%d').date()
    return None


def ajustar_caixa(cursor, usuario_id, mes, ano, delta):
    if not delta:
        return

    cursor.execute("""
        UPDATE FIN_Caixa
        SET SaldoAtual = ISNULL(SaldoAtual, 0) + ?, DataAtualizacao = GETDATE()
        WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
    """, (delta, usuario_id, mes, ano))

    if cursor.rowcount == 0:
        cursor.execute("""
            INSERT INTO FIN_Caixa (UsuarioId, MesReferencia, AnoReferencia, SaldoAtual, DataAtualizacao)
            VALUES (?, ?, ?, ?, GETDATE())
        """, (usuario_id, mes, ano, delta))


def garantir_categoria_financeira(cursor, usuario_id, nome, cor_hex):
    cursor.execute("""
        SELECT CategoriaId
        FROM FIN_Categorias
        WHERE UsuarioId = ? AND Nome = ?
    """, (usuario_id, nome))
    categoria = cursor.fetchone()

    if categoria:
        return categoria.CategoriaId

    cursor.execute("""
        INSERT INTO FIN_Categorias (UsuarioId, Nome, CorHex)
        VALUES (?, ?, ?)
    """, (usuario_id, nome, cor_hex))
    cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
    return int(cursor.fetchone()[0])


def data_vencimento_assinatura(data_renovacao, ciclo, mes, ano):
    data_base = normalizar_data(data_renovacao)
    if not data_base:
        return None

    ciclo = (ciclo or 'mensal').lower()
    periodo_base = chave_periodo(data_base.month, data_base.year)
    periodo_destino = chave_periodo(mes, ano)

    if periodo_destino < periodo_base:
        return None

    if ciclo == 'anual' and mes != data_base.month:
        return None

    ultimo_dia = monthrange(ano, mes)[1]
    return date(ano, mes, min(data_base.day, ultimo_dia))


def criar_lancamento_assinatura(cursor, usuario_id, assinatura, categoria_id, data_vencimento, mes, ano):
    descricao = f"Assinatura - {assinatura.Nome}"
    valor = float(assinatura.Valor or 0)

    cursor.execute("""
        INSERT INTO FIN_Lancamentos
        (UsuarioId, CategoriaId, Descricao, ValorEstimado, ValorReal,
         DataVencimento, MesReferencia, AnoReferencia, Pago)
        VALUES (?, ?, ?, ?, 0, ?, ?, ?, 0)
    """, (usuario_id, categoria_id, descricao, valor, data_vencimento, mes, ano))
    cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
    return int(cursor.fetchone()[0])


def sincronizar_assinaturas_periodo(cursor, usuario_id, mes, ano, assinatura_id=None):
    categoria_id = garantir_categoria_financeira(cursor, usuario_id, 'Assinaturas', '#7c3aed')

    params = [usuario_id]
    filtro_assinatura = ''
    if assinatura_id:
        filtro_assinatura = ' AND AssinaturaId = ?'
        params.append(assinatura_id)

    cursor.execute(f"""
        SELECT AssinaturaId, Nome, Valor, Ciclo, DataRenovacao, Ativa
        FROM FIN_Assinaturas
        WHERE UsuarioId = ? AND Ativa = 1{filtro_assinatura}
        ORDER BY Nome ASC
    """, tuple(params))
    assinaturas = cursor.fetchall()

    for assinatura in assinaturas:
        data_vencimento = data_vencimento_assinatura(assinatura.DataRenovacao, assinatura.Ciclo, mes, ano)
        if not data_vencimento:
            continue

        cursor.execute("""
            SELECT M.AssinaturaLancamentoId, M.LancamentoId, L.Pago,
                   ISNULL(M.Ignorado, 0) AS Ignorado
            FROM FIN_AssinaturaLancamentos M
            LEFT JOIN FIN_Lancamentos L
                ON L.LancamentoId = M.LancamentoId AND L.UsuarioId = M.UsuarioId
            WHERE M.UsuarioId = ? AND M.AssinaturaId = ?
              AND M.MesReferencia = ? AND M.AnoReferencia = ?
        """, (usuario_id, assinatura.AssinaturaId, mes, ano))
        vinculo = cursor.fetchone()

        if vinculo and vinculo.Ignorado:
            continue

        if vinculo and vinculo.Pago is not None:
            if not vinculo.Pago:
                cursor.execute("""
                    UPDATE FIN_Lancamentos
                    SET CategoriaId = ?, Descricao = ?, ValorEstimado = ?, DataVencimento = ?
                    WHERE LancamentoId = ? AND UsuarioId = ? AND Pago = 0
                """, (
                    categoria_id,
                    f"Assinatura - {assinatura.Nome}",
                    float(assinatura.Valor or 0),
                    data_vencimento,
                    vinculo.LancamentoId,
                    usuario_id,
                ))
            continue

        lancamento_id = criar_lancamento_assinatura(
            cursor, usuario_id, assinatura, categoria_id, data_vencimento, mes, ano
        )

        if vinculo:
            cursor.execute("""
                UPDATE FIN_AssinaturaLancamentos
                SET LancamentoId = ?, Ignorado = 0, DataSincronizacao = SYSUTCDATETIME()
                WHERE AssinaturaLancamentoId = ? AND UsuarioId = ?
            """, (lancamento_id, vinculo.AssinaturaLancamentoId, usuario_id))
        else:
            cursor.execute("""
                INSERT INTO FIN_AssinaturaLancamentos
                (UsuarioId, AssinaturaId, LancamentoId, MesReferencia, AnoReferencia)
                VALUES (?, ?, ?, ?, ?)
            """, (usuario_id, assinatura.AssinaturaId, lancamento_id, mes, ano))


def sincronizar_assinatura_primeiro_periodo(cursor, usuario_id, assinatura_id):
    cursor.execute("""
        SELECT DataRenovacao
        FROM FIN_Assinaturas
        WHERE UsuarioId = ? AND AssinaturaId = ? AND Ativa = 1
    """, (usuario_id, assinatura_id))
    assinatura = cursor.fetchone()

    if not assinatura:
        return

    data_renovacao = normalizar_data(assinatura.DataRenovacao)
    if data_renovacao:
        sincronizar_assinaturas_periodo(cursor, usuario_id, data_renovacao.month, data_renovacao.year, assinatura_id)


def remover_lancamentos_assinatura_pendentes(cursor, usuario_id, assinatura_id, remover_mapeamentos_pagos=False):
    cursor.execute("""
        SELECT M.AssinaturaLancamentoId, M.LancamentoId, L.Pago
        FROM FIN_AssinaturaLancamentos M
        LEFT JOIN FIN_Lancamentos L
            ON L.LancamentoId = M.LancamentoId AND L.UsuarioId = M.UsuarioId
        WHERE M.UsuarioId = ? AND M.AssinaturaId = ?
    """, (usuario_id, assinatura_id))
    vinculos = cursor.fetchall()

    for vinculo in vinculos:
        if vinculo.Pago is None or not vinculo.Pago:
            cursor.execute("""
                DELETE FROM FIN_Lancamentos
                WHERE LancamentoId = ? AND UsuarioId = ? AND Pago = 0
            """, (vinculo.LancamentoId, usuario_id))
            cursor.execute("""
                DELETE FROM FIN_AssinaturaLancamentos
                WHERE AssinaturaLancamentoId = ? AND UsuarioId = ?
            """, (vinculo.AssinaturaLancamentoId, usuario_id))
        elif remover_mapeamentos_pagos:
            cursor.execute("""
                DELETE FROM FIN_AssinaturaLancamentos
                WHERE AssinaturaLancamentoId = ? AND UsuarioId = ?
            """, (vinculo.AssinaturaLancamentoId, usuario_id))

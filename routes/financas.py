from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_cursor
from datetime import datetime, date
from zoneinfo import ZoneInfo
import calendar
from flask_login import current_user
from helpers.sql import placeholders_sql
from helpers.workspaces import usuarios_visiveis_financeiro
from routes.assinaturas import montar_resumo_assinaturas
from routes.financeiro_integracoes import sincronizar_assinaturas_periodo
from routes.metas import montar_resumo_metas

financas_bp = Blueprint('financas', __name__, url_prefix='/app/financeiro')
financas_legacy_bp = Blueprint('financas_legacy', __name__, url_prefix='/financas')


def usuario_atual_id():
    return int(current_user.get_id())


def destino_local_ou(default_endpoint, **valores):
    next_url = request.form.get('next') or request.args.get('next')
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for(default_endpoint, **valores)


@financas_legacy_bp.route('/dashboard')
@financas_legacy_bp.route('', strict_slashes=False)
def legacy_dashboard():
    return redirect(url_for('financas.dashboard', **request.args))


@financas_legacy_bp.route('/adicionar-gasto')
def legacy_adicionar_gasto():
    return redirect(url_for('financas.adicionar_gasto', **request.args))


@financas_legacy_bp.route('/rendas')
def legacy_rendas():
    return redirect(url_for('financas.gerenciar_rendas', **request.args))


@financas_legacy_bp.route('/carteiras')
def legacy_carteiras():
    return redirect(url_for('financas.carteiras', **request.args))


@financas_legacy_bp.route('/rendas/categorias')
def legacy_categorias_rendas():
    return redirect(url_for('financas.categorias_rendas', **request.args))


@financas_legacy_bp.route('/rendas/recorrentes')
def legacy_rendas_recorrentes():
    return redirect(url_for('financas.rendas_recorrentes', **request.args))


@financas_legacy_bp.route('/lancamentos/recorrentes')
def legacy_lancamentos_recorrentes():
    return redirect(url_for('financas.lancamentos_recorrentes', **request.args))


@financas_legacy_bp.route('/categorias')
def legacy_categorias():
    return redirect(url_for('financas.categorias', **request.args))


def parse_money(valor, default=0.0):
    if valor is None:
        return default

    valor_limpo = str(valor).replace('R$', '').replace(' ', '')
    if ',' in valor_limpo:
        valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
    try:
        return float(valor_limpo) if valor_limpo else default
    except ValueError:
        return default


def parse_money_strict(valor):
    if valor is None or str(valor).strip() == '':
        raise ValueError

    valor_limpo = str(valor).replace('R$', '').replace(' ', '')
    if ',' in valor_limpo:
        valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
    return float(valor_limpo)


MESES_LISTA = [
    (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
    (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
    (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
]

NOMES_MESES = dict(MESES_LISTA)
COR_CATEGORIA_PADRAO = '#6c757d'
CORES_CATEGORIA_SUGERIDAS = [
    '#0d6efd', '#198754', '#dc3545', '#fd7e14',
    '#6f42c1', '#20c997', '#0dcaf0', '#ffc107',
    '#d63384', '#6c757d', '#0f172a', '#8b5cf6',
]
TIPOS_CARTEIRA = [
    ('conta_corrente', 'Conta corrente'),
    ('poupanca', 'Poupanca'),
    ('carteira', 'Dinheiro/carteira'),
    ('investimento', 'Investimento'),
    ('empresa', 'Conta da empresa'),
    ('outro', 'Outro'),
]
PERIODICIDADES_RENDA = {
    'mensal': {'label': 'Mensal', 'meses': 1},
    'bimestral': {'label': 'Bimestral', 'meses': 2},
    'trimestral': {'label': 'Trimestral', 'meses': 3},
    'semestral': {'label': 'Semestral', 'meses': 6},
    'anual': {'label': 'Anual', 'meses': 12},
    'personalizado': {'label': 'Personalizado', 'meses': None},
}


def periodo_atual():
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))
    return hoje.month, hoje.year


def normalizar_cor_categoria(cor):
    cor = (cor or COR_CATEGORIA_PADRAO).strip()
    digitos_hex = '0123456789abcdefABCDEF'
    if len(cor) == 7 and cor.startswith('#') and all(c in digitos_hex for c in cor[1:]):
        return cor.lower()
    return COR_CATEGORIA_PADRAO


def tipo_carteira_valido(tipo):
    tipos_validos = {item[0] for item in TIPOS_CARTEIRA}
    return tipo if tipo in tipos_validos else 'outro'


def periodicidade_renda_valida(periodicidade):
    return periodicidade if periodicidade in PERIODICIDADES_RENDA else 'mensal'


def intervalo_renda(periodicidade, intervalo_personalizado=None):
    periodicidade = periodicidade_renda_valida(periodicidade)
    if periodicidade != 'personalizado':
        return PERIODICIDADES_RENDA[periodicidade]['meses']

    try:
        return max(int(intervalo_personalizado or 1), 1)
    except (TypeError, ValueError):
        return 1


def rotulo_periodicidade_renda(periodicidade, intervalo_meses):
    periodicidade = periodicidade_renda_valida(periodicidade)
    if periodicidade == 'personalizado':
        return f'A cada {intervalo_meses or 1} meses'
    return PERIODICIDADES_RENDA[periodicidade]['label']


def normalizar_periodo(mes=None, ano=None):
    mes_atual, ano_atual = periodo_atual()
    mes = mes or mes_atual
    ano = ano or ano_atual

    if mes < 1:
        ano -= 1
        mes = 12
    elif mes > 12:
        ano += 1
        mes = 1

    return mes, ano


def periodo_anterior(mes, ano):
    return (12, ano - 1) if mes == 1 else (mes - 1, ano)


def periodo_proximo(mes, ano):
    return (1, ano + 1) if mes == 12 else (mes + 1, ano)


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


def data_vencimento_no_destino(data_origem, mes_destino, ano_destino):
    dia_origem = getattr(data_origem, 'day', None) or 10
    ultimo_dia = calendar.monthrange(ano_destino, mes_destino)[1]
    dia = min(dia_origem, ultimo_dia)
    return date(ano_destino, mes_destino, dia)


def data_recebimento_recorrente(renda_recorrente, mes, ano):
    data_inicio = normalizar_data(renda_recorrente.DataInicio)
    if not data_inicio:
        return None

    periodo_inicio = chave_periodo(data_inicio.month, data_inicio.year)
    periodo_destino = chave_periodo(mes, ano)
    if periodo_destino < periodo_inicio:
        return None

    intervalo = max(int(renda_recorrente.IntervaloMeses or 1), 1)
    if (periodo_destino - periodo_inicio) % intervalo != 0:
        return None

    dia = min(int(renda_recorrente.DiaRecebimento or data_inicio.day), calendar.monthrange(ano, mes)[1])
    data_ocorrencia = date(ano, mes, dia)
    data_fim = normalizar_data(renda_recorrente.DataFim)
    if data_fim and data_ocorrencia > data_fim:
        return None

    return data_ocorrencia


def data_vencimento_recorrente(lancamento_recorrente, mes, ano):
    data_inicio = normalizar_data(lancamento_recorrente.DataInicio)
    if not data_inicio:
        return None

    periodo_inicio = chave_periodo(data_inicio.month, data_inicio.year)
    periodo_destino = chave_periodo(mes, ano)
    if periodo_destino < periodo_inicio:
        return None

    intervalo = max(int(lancamento_recorrente.IntervaloMeses or 1), 1)
    if (periodo_destino - periodo_inicio) % intervalo != 0:
        return None

    dia = min(int(lancamento_recorrente.DiaVencimento or data_inicio.day), calendar.monthrange(ano, mes)[1])
    data_ocorrencia = date(ano, mes, dia)
    data_fim = normalizar_data(lancamento_recorrente.DataFim)
    if data_fim and data_ocorrencia > data_fim:
        return None

    return data_ocorrencia


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


def obter_resumo_carteiras(cursor, usuario_id):
    cursor.execute("""
        SELECT
            COUNT(*) AS TotalCarteiras,
            SUM(CASE WHEN Ativa = 1 THEN 1 ELSE 0 END) AS Ativas,
            SUM(CASE WHEN Ativa = 1 THEN ISNULL(SaldoAtual, 0) ELSE 0 END) AS SaldoTotal
        FROM FIN_Carteiras
        WHERE UsuarioId = ?
    """, (usuario_id,))
    resumo = cursor.fetchone()
    return {
        'total': int(resumo.TotalCarteiras or 0) if resumo else 0,
        'ativas': int(resumo.Ativas or 0) if resumo else 0,
        'saldo_total': float(resumo.SaldoTotal or 0) if resumo else 0.0,
    }


def listar_carteiras_ativas(cursor, usuario_id):
    cursor.execute("""
        SELECT CarteiraId, Nome, Tipo, SaldoAtual, CorHex
        FROM FIN_Carteiras
        WHERE UsuarioId = ? AND Ativa = 1
        ORDER BY Nome
    """, (usuario_id,))
    return cursor.fetchall()


def carteira_ativa_existe(cursor, usuario_id, carteira_id):
    if not carteira_id:
        return False

    cursor.execute("""
        SELECT CarteiraId
        FROM FIN_Carteiras
        WHERE CarteiraId = ? AND UsuarioId = ? AND Ativa = 1
    """, (carteira_id, usuario_id))
    return cursor.fetchone() is not None


def movimentar_carteira(cursor, usuario_id, carteira_id, delta):
    if not carteira_id or not delta:
        return False

    cursor.execute("""
        UPDATE FIN_Carteiras
        SET SaldoAtual = ISNULL(SaldoAtual, 0) + ?,
            DataAtualizacao = SYSUTCDATETIME()
        WHERE CarteiraId = ? AND UsuarioId = ? AND Ativa = 1
    """, (delta, carteira_id, usuario_id))
    return cursor.rowcount > 0


def ignorar_sincronizacao_assinatura_lancamento(cursor, usuario_id, lancamento_id):
    cursor.execute("""
        UPDATE FIN_AssinaturaLancamentos
        SET Ignorado = 1,
            DataSincronizacao = SYSUTCDATETIME()
        WHERE LancamentoId = ? AND UsuarioId = ?
    """, (lancamento_id, usuario_id))


def ignorar_sincronizacao_lancamento_recorrente(cursor, usuario_id, lancamento_id):
    cursor.execute("""
        UPDATE FIN_LancamentoRecorrenteOcorrencias
        SET Ignorado = 1,
            DataSincronizacao = SYSUTCDATETIME()
        WHERE LancamentoId = ? AND UsuarioId = ?
    """, (lancamento_id, usuario_id))


def sincronizar_caixa_com_carteiras(cursor, usuario_id, mes, ano):
    resumo = obter_resumo_carteiras(cursor, usuario_id)
    if resumo['ativas'] == 0:
        return None

    cursor.execute("""
        UPDATE FIN_Caixa
        SET SaldoAtual = ?, DataAtualizacao = GETDATE()
        WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
    """, (resumo['saldo_total'], usuario_id, mes, ano))

    if cursor.rowcount == 0:
        cursor.execute("""
            INSERT INTO FIN_Caixa (UsuarioId, MesReferencia, AnoReferencia, SaldoAtual, DataAtualizacao)
            VALUES (?, ?, ?, ?, GETDATE())
        """, (usuario_id, mes, ano, resumo['saldo_total']))

    return resumo['saldo_total']


def criar_ocorrencia_renda_recorrente(cursor, usuario_id, renda_recorrente, data_recebimento, mes, ano):
    carteira_id = renda_recorrente.CarteiraId
    if not carteira_ativa_existe(cursor, usuario_id, carteira_id):
        carteira_id = None

    cursor.execute("""
        INSERT INTO FIN_Rendas
        (UsuarioId, CategoriaRendaId, CarteiraId, RendaRecorrenteId, Descricao,
         ValorPrevisto, ValorReal, DataRecebimento, MesReferencia, AnoReferencia)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
    """, (
        usuario_id,
        renda_recorrente.CategoriaRendaId,
        carteira_id,
        renda_recorrente.RendaRecorrenteId,
        renda_recorrente.Descricao,
        float(renda_recorrente.ValorPrevisto or 0),
        data_recebimento,
        mes,
        ano,
    ))
    cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
    return int(cursor.fetchone()[0])


def sincronizar_rendas_recorrentes_periodo(cursor, usuario_id, mes, ano, renda_recorrente_id=None):
    params = [usuario_id]
    filtro = ''
    if renda_recorrente_id:
        filtro = ' AND RendaRecorrenteId = ?'
        params.append(renda_recorrente_id)

    cursor.execute(f"""
        SELECT RendaRecorrenteId, UsuarioId, CategoriaRendaId, CarteiraId, Descricao,
               ValorPrevisto, DiaRecebimento, Periodicidade, IntervaloMeses,
               DataInicio, DataFim, Ativa
        FROM FIN_RendasRecorrentes
        WHERE UsuarioId = ? AND Ativa = 1{filtro}
        ORDER BY Descricao ASC
    """, tuple(params))
    recorrentes = cursor.fetchall()

    for recorrente in recorrentes:
        data_recebimento = data_recebimento_recorrente(recorrente, mes, ano)
        if not data_recebimento:
            continue

        cursor.execute("""
            SELECT O.OcorrenciaId, O.RendaId, R.RendaId AS RendaExistente
            FROM FIN_RendaRecorrenteOcorrencias O
            LEFT JOIN FIN_Rendas R
                ON R.RendaId = O.RendaId AND R.UsuarioId = O.UsuarioId
            WHERE O.UsuarioId = ? AND O.RendaRecorrenteId = ?
              AND O.MesReferencia = ? AND O.AnoReferencia = ?
        """, (usuario_id, recorrente.RendaRecorrenteId, mes, ano))
        ocorrencia = cursor.fetchone()

        if ocorrencia and ocorrencia.RendaExistente:
            continue

        renda_id = criar_ocorrencia_renda_recorrente(cursor, usuario_id, recorrente, data_recebimento, mes, ano)

        if ocorrencia:
            cursor.execute("""
                UPDATE FIN_RendaRecorrenteOcorrencias
                SET RendaId = ?, DataSincronizacao = SYSUTCDATETIME()
                WHERE OcorrenciaId = ? AND UsuarioId = ?
            """, (renda_id, ocorrencia.OcorrenciaId, usuario_id))
        else:
            cursor.execute("""
                INSERT INTO FIN_RendaRecorrenteOcorrencias
                (UsuarioId, RendaRecorrenteId, RendaId, MesReferencia, AnoReferencia)
                VALUES (?, ?, ?, ?, ?)
            """, (usuario_id, recorrente.RendaRecorrenteId, renda_id, mes, ano))


def criar_ocorrencia_lancamento_recorrente(cursor, usuario_id, lancamento_recorrente, data_vencimento, mes, ano):
    cursor.execute("""
        INSERT INTO FIN_Lancamentos
        (UsuarioId, CategoriaId, LancamentoRecorrenteId, Descricao, ValorEstimado, ValorReal,
         DataVencimento, MesReferencia, AnoReferencia, Pago)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 0)
    """, (
        usuario_id,
        lancamento_recorrente.CategoriaId,
        lancamento_recorrente.LancamentoRecorrenteId,
        lancamento_recorrente.Descricao,
        float(lancamento_recorrente.ValorEstimado or 0),
        data_vencimento,
        mes,
        ano,
    ))
    cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
    return int(cursor.fetchone()[0])


def sincronizar_lancamentos_recorrentes_periodo(cursor, usuario_id, mes, ano, lancamento_recorrente_id=None):
    params = [usuario_id]
    filtro = ''
    if lancamento_recorrente_id:
        filtro = ' AND LancamentoRecorrenteId = ?'
        params.append(lancamento_recorrente_id)

    cursor.execute(f"""
        SELECT LancamentoRecorrenteId, UsuarioId, CategoriaId, Descricao,
               ValorEstimado, DiaVencimento, Periodicidade, IntervaloMeses,
               DataInicio, DataFim, Ativa
        FROM FIN_LancamentosRecorrentes
        WHERE UsuarioId = ? AND Ativa = 1{filtro}
        ORDER BY Descricao ASC
    """, tuple(params))
    recorrentes = cursor.fetchall()

    for recorrente in recorrentes:
        data_vencimento = data_vencimento_recorrente(recorrente, mes, ano)
        if not data_vencimento:
            continue

        cursor.execute("""
            SELECT O.OcorrenciaId, O.LancamentoId, L.LancamentoId AS LancamentoExistente,
                   ISNULL(O.Ignorado, 0) AS Ignorado
            FROM FIN_LancamentoRecorrenteOcorrencias O
            LEFT JOIN FIN_Lancamentos L
                ON L.LancamentoId = O.LancamentoId AND L.UsuarioId = O.UsuarioId
            WHERE O.UsuarioId = ? AND O.LancamentoRecorrenteId = ?
              AND O.MesReferencia = ? AND O.AnoReferencia = ?
        """, (usuario_id, recorrente.LancamentoRecorrenteId, mes, ano))
        ocorrencia = cursor.fetchone()

        if ocorrencia and ocorrencia.Ignorado:
            continue

        if ocorrencia and ocorrencia.LancamentoExistente:
            continue

        lancamento_id = criar_ocorrencia_lancamento_recorrente(
            cursor, usuario_id, recorrente, data_vencimento, mes, ano
        )

        if ocorrencia:
            cursor.execute("""
                UPDATE FIN_LancamentoRecorrenteOcorrencias
                SET LancamentoId = ?, Ignorado = 0, DataSincronizacao = SYSUTCDATETIME()
                WHERE OcorrenciaId = ? AND UsuarioId = ?
            """, (lancamento_id, ocorrencia.OcorrenciaId, usuario_id))
        else:
            cursor.execute("""
                INSERT INTO FIN_LancamentoRecorrenteOcorrencias
                (UsuarioId, LancamentoRecorrenteId, LancamentoId, MesReferencia, AnoReferencia)
                VALUES (?, ?, ?, ?, ?)
            """, (usuario_id, recorrente.LancamentoRecorrenteId, lancamento_id, mes, ano))


def sincronizar_lancamento_recorrente_primeiro_periodo(cursor, usuario_id, lancamento_recorrente_id):
    cursor.execute("""
        SELECT DataInicio
        FROM FIN_LancamentosRecorrentes
        WHERE UsuarioId = ? AND LancamentoRecorrenteId = ? AND Ativa = 1
    """, (usuario_id, lancamento_recorrente_id))
    recorrente = cursor.fetchone()

    if not recorrente:
        return

    data_inicio = normalizar_data(recorrente.DataInicio)
    if data_inicio:
        sincronizar_lancamentos_recorrentes_periodo(
            cursor, usuario_id, data_inicio.month, data_inicio.year, lancamento_recorrente_id
        )


def sincronizar_renda_recorrente_primeiro_periodo(cursor, usuario_id, renda_recorrente_id):
    cursor.execute("""
        SELECT DataInicio
        FROM FIN_RendasRecorrentes
        WHERE UsuarioId = ? AND RendaRecorrenteId = ? AND Ativa = 1
    """, (usuario_id, renda_recorrente_id))
    recorrente = cursor.fetchone()

    if not recorrente:
        return

    data_inicio = normalizar_data(recorrente.DataInicio)
    if data_inicio:
        sincronizar_rendas_recorrentes_periodo(
            cursor, usuario_id, data_inicio.month, data_inicio.year, renda_recorrente_id
        )


def remover_ocorrencias_renda_recorrente_pendentes(cursor, usuario_id, renda_recorrente_id):
    cursor.execute("""
        SELECT O.OcorrenciaId, O.RendaId, ISNULL(R.ValorReal, 0) AS ValorReal
        FROM FIN_RendaRecorrenteOcorrencias O
        LEFT JOIN FIN_Rendas R
            ON R.RendaId = O.RendaId AND R.UsuarioId = O.UsuarioId
        WHERE O.UsuarioId = ? AND O.RendaRecorrenteId = ?
    """, (usuario_id, renda_recorrente_id))
    ocorrencias = cursor.fetchall()

    for ocorrencia in ocorrencias:
        valor_real = float(ocorrencia.ValorReal or 0)
        if valor_real <= 0:
            cursor.execute("""
                DELETE FROM FIN_Rendas
                WHERE RendaId = ? AND UsuarioId = ? AND ISNULL(ValorReal, 0) <= 0
            """, (ocorrencia.RendaId, usuario_id))
            cursor.execute("""
                DELETE FROM FIN_RendaRecorrenteOcorrencias
                WHERE OcorrenciaId = ? AND UsuarioId = ?
            """, (ocorrencia.OcorrenciaId, usuario_id))


def remover_ocorrencias_lancamento_recorrente_pendentes(cursor, usuario_id, lancamento_recorrente_id):
    cursor.execute("""
        SELECT O.OcorrenciaId, O.LancamentoId, ISNULL(L.ValorReal, 0) AS ValorReal, L.Pago
        FROM FIN_LancamentoRecorrenteOcorrencias O
        LEFT JOIN FIN_Lancamentos L
            ON L.LancamentoId = O.LancamentoId AND L.UsuarioId = O.UsuarioId
        WHERE O.UsuarioId = ? AND O.LancamentoRecorrenteId = ?
    """, (usuario_id, lancamento_recorrente_id))
    ocorrencias = cursor.fetchall()

    for ocorrencia in ocorrencias:
        if ocorrencia.Pago is None or not ocorrencia.Pago:
            cursor.execute("""
                DELETE FROM FIN_Lancamentos
                WHERE LancamentoId = ? AND UsuarioId = ? AND Pago = 0
            """, (ocorrencia.LancamentoId, usuario_id))
            cursor.execute("""
                DELETE FROM FIN_LancamentoRecorrenteOcorrencias
                WHERE OcorrenciaId = ? AND UsuarioId = ?
            """, (ocorrencia.OcorrenciaId, usuario_id))


def total_ocorrencias_renda_recorrente_recebidas(cursor, usuario_id, renda_recorrente_id):
    cursor.execute("""
        SELECT COUNT(*)
        FROM FIN_RendaRecorrenteOcorrencias O
        JOIN FIN_Rendas R
            ON R.RendaId = O.RendaId AND R.UsuarioId = O.UsuarioId
        WHERE O.UsuarioId = ? AND O.RendaRecorrenteId = ?
          AND ISNULL(R.ValorReal, 0) > 0
    """, (usuario_id, renda_recorrente_id))
    return int(cursor.fetchone()[0] or 0)


def total_ocorrencias_lancamento_recorrente_pagas(cursor, usuario_id, lancamento_recorrente_id):
    cursor.execute("""
        SELECT COUNT(*)
        FROM FIN_LancamentoRecorrenteOcorrencias O
        JOIN FIN_Lancamentos L
            ON L.LancamentoId = O.LancamentoId AND L.UsuarioId = O.UsuarioId
        WHERE O.UsuarioId = ? AND O.LancamentoRecorrenteId = ?
          AND L.Pago = 1
    """, (usuario_id, lancamento_recorrente_id))
    return int(cursor.fetchone()[0] or 0)


def ler_dados_renda_recorrente_form():
    descricao = (request.form.get('descricao') or '').strip()
    if not descricao:
        return None, 'Informe a descricao da renda recorrente.'

    valor_previsto = parse_money(request.form.get('valor_previsto'))
    if valor_previsto < 0:
        return None, 'Informe um valor previsto maior ou igual a zero.'

    try:
        data_inicio = normalizar_data(request.form.get('data_inicio'))
    except (TypeError, ValueError):
        return None, 'Informe uma data de inicio valida.'

    if not data_inicio:
        return None, 'Informe a data de inicio da recorrencia.'

    try:
        data_fim = normalizar_data(request.form.get('data_fim')) if request.form.get('data_fim') else None
    except (TypeError, ValueError):
        return None, 'Informe uma data final valida.'

    if data_fim and data_fim < data_inicio:
        return None, 'A data final precisa ser maior ou igual a data de inicio.'

    periodicidade = periodicidade_renda_valida(request.form.get('periodicidade') or 'mensal')
    intervalo_meses = intervalo_renda(periodicidade, request.form.get('intervalo_meses'))

    try:
        dia_recebimento = int(request.form.get('dia_recebimento') or data_inicio.day)
    except (TypeError, ValueError):
        dia_recebimento = data_inicio.day
    dia_recebimento = min(max(dia_recebimento, 1), 31)

    return {
        'descricao': descricao[:140],
        'categoria_renda_id': request.form.get('categoria_renda_id') or None,
        'carteira_id': request.form.get('carteira_id') or None,
        'valor_previsto': valor_previsto,
        'dia_recebimento': dia_recebimento,
        'periodicidade': periodicidade,
        'intervalo_meses': intervalo_meses,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'ativa': 1 if request.form.get('ativa', 'on') == 'on' else 0,
    }, None


def ler_dados_lancamento_recorrente_form():
    descricao = (request.form.get('descricao') or '').strip()
    if not descricao:
        return None, 'Informe a descricao da despesa recorrente.'

    valor_estimado = parse_money(request.form.get('valor_estimado'))
    if valor_estimado < 0:
        return None, 'Informe um valor estimado maior ou igual a zero.'

    try:
        data_inicio = normalizar_data(request.form.get('data_inicio'))
    except (TypeError, ValueError):
        return None, 'Informe uma data de inicio valida.'

    if not data_inicio:
        return None, 'Informe a data de inicio da recorrencia.'

    try:
        data_fim = normalizar_data(request.form.get('data_fim')) if request.form.get('data_fim') else None
    except (TypeError, ValueError):
        return None, 'Informe uma data final valida.'

    if data_fim and data_fim < data_inicio:
        return None, 'A data final precisa ser maior ou igual a data de inicio.'

    periodicidade = periodicidade_renda_valida(request.form.get('periodicidade') or 'mensal')
    intervalo_meses = intervalo_renda(periodicidade, request.form.get('intervalo_meses'))

    try:
        dia_vencimento = int(request.form.get('dia_vencimento') or data_inicio.day)
    except (TypeError, ValueError):
        dia_vencimento = data_inicio.day
    dia_vencimento = min(max(dia_vencimento, 1), 31)

    return {
        'descricao': descricao[:140],
        'categoria_id': request.form.get('categoria_id') or None,
        'valor_estimado': valor_estimado,
        'dia_vencimento': dia_vencimento,
        'periodicidade': periodicidade,
        'intervalo_meses': intervalo_meses,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'ativa': 1 if request.form.get('ativa', 'on') == 'on' else 0,
    }, None


def criar_regra_recorrente_a_partir_lancamento(cursor, usuario_id, lancamento_id, dados_lancamento):
    cursor.execute("""
        SELECT ISNULL(L.LancamentoRecorrenteId, O.LancamentoRecorrenteId) AS LancamentoRecorrenteId
        FROM FIN_Lancamentos L
        LEFT JOIN FIN_LancamentoRecorrenteOcorrencias O
            ON O.LancamentoId = L.LancamentoId AND O.UsuarioId = L.UsuarioId
        WHERE L.LancamentoId = ? AND L.UsuarioId = ?
    """, (lancamento_id, usuario_id))
    existente = cursor.fetchone()
    if existente and existente.LancamentoRecorrenteId:
        return existente.LancamentoRecorrenteId

    data_inicio = dados_lancamento['data_vencimento']
    cursor.execute("""
        INSERT INTO FIN_LancamentosRecorrentes
        (UsuarioId, CategoriaId, Descricao, ValorEstimado, DiaVencimento,
         Periodicidade, IntervaloMeses, DataInicio, DataFim, Ativa)
        VALUES (?, ?, ?, ?, ?, 'mensal', 1, ?, NULL, 1)
    """, (
        usuario_id,
        dados_lancamento['categoria_id'],
        dados_lancamento['descricao'],
        dados_lancamento['valor_estimado'],
        data_inicio.day,
        data_inicio,
    ))
    cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
    recorrente_id = int(cursor.fetchone()[0])

    cursor.execute("""
        UPDATE FIN_Lancamentos
        SET LancamentoRecorrenteId = ?
        WHERE LancamentoId = ? AND UsuarioId = ?
    """, (recorrente_id, lancamento_id, usuario_id))

    cursor.execute("""
        INSERT INTO FIN_LancamentoRecorrenteOcorrencias
        (UsuarioId, LancamentoRecorrenteId, LancamentoId, MesReferencia, AnoReferencia)
        VALUES (?, ?, ?, ?, ?)
    """, (
        usuario_id,
        recorrente_id,
        lancamento_id,
        data_inicio.month,
        data_inicio.year,
    ))
    return recorrente_id


def periodo_por_chave(chave):
    ano = (chave - 1) // 12
    mes = chave - (ano * 12)
    return mes, ano


def saldo_transportado_periodo(cursor, usuario_id, mes, ano, profundidade=12, usuarios_ids=None):
    if profundidade <= 0:
        return 0.0

    usuarios_ids = usuarios_ids or [usuario_id]
    usuarios_placeholders = placeholders_sql(usuarios_ids)
    chave_atual = chave_periodo(mes, ano)
    chave_inicio = chave_atual - profundidade
    chave_fim = chave_atual - 1
    mes_inicio, ano_inicio = periodo_por_chave(chave_inicio)
    mes_fim, ano_fim = periodo_por_chave(chave_fim)
    params_periodo = tuple(usuarios_ids) + (
        ano_inicio, ano_inicio, mes_inicio,
        ano_fim, ano_fim, mes_fim,
    )
    resumos = {}

    for chave in range(chave_inicio, chave_fim + 1):
        mes_ref, ano_ref = periodo_por_chave(chave)
        resumos[chave] = {
            'mes': mes_ref,
            'ano': ano_ref,
            'saldo_bancario': 0.0,
            'rendas_a_receber': 0.0,
            'contas_pendentes': 0.0,
        }

    cursor.execute(f"""
        SELECT
            MesReferencia,
            AnoReferencia,
            SUM(SaldoBancario) AS SaldoBancario,
            SUM(RendasAReceber) AS RendasAReceber,
            SUM(ContasPendentes) AS ContasPendentes
        FROM (
            SELECT
                MesReferencia,
                AnoReferencia,
                SUM(ISNULL(SaldoAtual, 0)) AS SaldoBancario,
                0 AS RendasAReceber,
                0 AS ContasPendentes
            FROM FIN_Caixa
            WHERE UsuarioId IN ({usuarios_placeholders})
            AND (AnoReferencia > ? OR (AnoReferencia = ? AND MesReferencia >= ?))
            AND (AnoReferencia < ? OR (AnoReferencia = ? AND MesReferencia <= ?))
            GROUP BY MesReferencia, AnoReferencia

            UNION ALL

            SELECT
                MesReferencia,
                AnoReferencia,
                0 AS SaldoBancario,
                SUM(
                    CASE
                        WHEN ISNULL(ValorReal, 0) > 0 THEN 0
                        ELSE ISNULL(ValorPrevisto, 0)
                    END
                ) AS RendasAReceber,
                0 AS ContasPendentes
            FROM FIN_Rendas
            WHERE UsuarioId IN ({usuarios_placeholders})
            AND (AnoReferencia > ? OR (AnoReferencia = ? AND MesReferencia >= ?))
            AND (AnoReferencia < ? OR (AnoReferencia = ? AND MesReferencia <= ?))
            GROUP BY MesReferencia, AnoReferencia

            UNION ALL

            SELECT
                MesReferencia,
                AnoReferencia,
                0 AS SaldoBancario,
                0 AS RendasAReceber,
                SUM(ISNULL(ValorEstimado, 0)) AS ContasPendentes
            FROM FIN_Lancamentos
            WHERE UsuarioId IN ({usuarios_placeholders}) AND Pago = 0
            AND (AnoReferencia > ? OR (AnoReferencia = ? AND MesReferencia >= ?))
            AND (AnoReferencia < ? OR (AnoReferencia = ? AND MesReferencia <= ?))
            GROUP BY MesReferencia, AnoReferencia
        ) resumo
        GROUP BY MesReferencia, AnoReferencia
    """, params_periodo * 3)
    for item in cursor.fetchall():
        chave = chave_periodo(item.MesReferencia, item.AnoReferencia)
        if chave in resumos:
            resumos[chave]['saldo_bancario'] = float(item.SaldoBancario or 0)
            resumos[chave]['rendas_a_receber'] = float(item.RendasAReceber or 0)
            resumos[chave]['contas_pendentes'] = float(item.ContasPendentes or 0)

    saldo_transportado = 0.0
    for chave in range(chave_inicio, chave_fim + 1):
        resumo = resumos[chave]
        sobra = (
            resumo['saldo_bancario']
            + saldo_transportado
            + resumo['rendas_a_receber']
            - resumo['contas_pendentes']
        )
        saldo_transportado = max(sobra, 0.0)

    return saldo_transportado


def montar_fluxo_caixa_diario(cursor, usuario_id, mes, ano, saldo_disponivel, usuarios_ids=None):
    usuarios_ids = usuarios_ids or [usuario_id]
    usuarios_placeholders = placeholders_sql(usuarios_ids)
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    entradas_por_dia = {dia: 0.0 for dia in range(1, ultimo_dia + 1)}
    saidas_por_dia = {dia: 0.0 for dia in range(1, ultimo_dia + 1)}
    entradas_recebidas = 0.0
    saidas_pagas = 0.0

    cursor.execute(f"""
        SELECT Descricao, ValorPrevisto, ISNULL(ValorReal, 0) AS ValorReal, DataRecebimento
        FROM FIN_Rendas
        WHERE UsuarioId IN ({usuarios_placeholders}) AND MesReferencia = ? AND AnoReferencia = ?
        ORDER BY DataRecebimento, RendaId
    """, tuple(usuarios_ids) + (mes, ano))
    rendas_periodo = cursor.fetchall()

    for renda in rendas_periodo:
        data_ref = normalizar_data(renda.DataRecebimento) or date(ano, mes, 1)
        dia = min(max(data_ref.day, 1), ultimo_dia)
        valor_real = float(renda.ValorReal or 0)
        valor_previsto = float(renda.ValorPrevisto or 0)
        valor = valor_real if valor_real > 0 else valor_previsto
        if valor <= 0:
            continue
        entradas_por_dia[dia] += valor
        if valor_real > 0:
            entradas_recebidas += valor_real

    cursor.execute(f"""
        SELECT Descricao, ValorEstimado, ISNULL(ValorReal, 0) AS ValorReal, Pago, DataVencimento
        FROM FIN_Lancamentos
        WHERE UsuarioId IN ({usuarios_placeholders}) AND MesReferencia = ? AND AnoReferencia = ?
        ORDER BY DataVencimento, LancamentoId
    """, tuple(usuarios_ids) + (mes, ano))
    lancamentos_periodo = cursor.fetchall()

    for lancamento in lancamentos_periodo:
        data_ref = normalizar_data(lancamento.DataVencimento) or date(ano, mes, 1)
        dia = min(max(data_ref.day, 1), ultimo_dia)
        valor_real = float(lancamento.ValorReal or 0)
        valor_estimado = float(lancamento.ValorEstimado or 0)
        pago = bool(lancamento.Pago)
        valor = valor_real if pago and valor_real > 0 else valor_estimado
        if valor <= 0:
            continue
        saidas_por_dia[dia] += valor
        if pago and valor_real > 0:
            saidas_pagas += valor_real

    saldo_inicial = float(saldo_disponivel or 0) - entradas_recebidas + saidas_pagas
    saldo_dia = saldo_inicial
    labels = []
    entradas = []
    saidas = []
    saldos = []
    saldo_minimo = None
    dia_saldo_minimo = None
    primeiro_risco = None
    saldo_primeiro_risco = None

    for dia in range(1, ultimo_dia + 1):
        saldo_dia += entradas_por_dia[dia]
        saldo_dia -= saidas_por_dia[dia]
        saldo_arredondado = round(saldo_dia, 2)

        labels.append(f'{dia:02d}/{mes:02d}')
        entradas.append(round(entradas_por_dia[dia], 2))
        saidas.append(round(saidas_por_dia[dia], 2))
        saldos.append(saldo_arredondado)

        if saldo_minimo is None or saldo_arredondado < saldo_minimo:
            saldo_minimo = saldo_arredondado
            dia_saldo_minimo = dia

        if primeiro_risco is None and saldo_arredondado < 0:
            primeiro_risco = dia
            saldo_primeiro_risco = saldo_arredondado

    return {
        'labels': labels,
        'saldos': saldos,
        'entradas': entradas,
        'saidas': saidas,
        'saidas_negativas': [-valor for valor in saidas],
        'saldo_inicial': round(saldo_inicial, 2),
        'saldo_final': saldos[-1] if saldos else round(saldo_inicial, 2),
        'saldo_minimo': saldo_minimo if saldo_minimo is not None else round(saldo_inicial, 2),
        'dia_saldo_minimo': dia_saldo_minimo,
        'primeiro_dia_negativo': primeiro_risco,
        'saldo_primeiro_dia_negativo': saldo_primeiro_risco,
        'risco_descoberto': primeiro_risco is not None,
        'total_entradas': round(sum(entradas), 2),
        'total_saidas': round(sum(saidas), 2),
    }


@financas_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))


@financas_bp.route('/carteiras', methods=['GET', 'POST'])
def carteiras():
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        tipo = tipo_carteira_valido(request.form.get('tipo') or 'conta_corrente')
        saldo_atual = parse_money(request.form.get('saldo_atual'))
        cor_hex = normalizar_cor_categoria(request.form.get('cor_hex') or '#0d6efd')

        if not nome:
            flash('Informe o nome da carteira.', 'danger')
            return redirect(url_for('financas.carteiras'))

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT CarteiraId
                FROM FIN_Carteiras
                WHERE UsuarioId = ? AND Nome = ?
            """, (usuario_id, nome[:100]))
            if cursor.fetchone():
                flash('Voce ja possui uma carteira com esse nome.', 'warning')
                return redirect(url_for('financas.carteiras'))

            cursor.execute("""
                INSERT INTO FIN_Carteiras (UsuarioId, Nome, Tipo, SaldoAtual, CorHex, Ativa)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (usuario_id, nome[:100], tipo, saldo_atual, cor_hex))
            sincronizar_caixa_com_carteiras(cursor, usuario_id, mes_atual, ano_atual)

        flash('Carteira criada com sucesso.', 'success')
        return redirect(url_for('financas.carteiras'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                C.CarteiraId,
                C.Nome,
                C.Tipo,
                C.SaldoAtual,
                C.CorHex,
                C.Ativa,
                ISNULL(R.TotalRendas, 0) AS TotalRendas,
                ISNULL(L.TotalLancamentos, 0) AS TotalLancamentos
            FROM FIN_Carteiras C
            OUTER APPLY (
                SELECT COUNT(*) AS TotalRendas
                FROM FIN_Rendas R
                WHERE R.CarteiraId = C.CarteiraId AND R.UsuarioId = C.UsuarioId
            ) R
            OUTER APPLY (
                SELECT COUNT(*) AS TotalLancamentos
                FROM FIN_Lancamentos L
                WHERE L.CarteiraId = C.CarteiraId AND L.UsuarioId = C.UsuarioId
            ) L
            WHERE C.UsuarioId = ?
            ORDER BY C.Ativa DESC, C.Nome
        """, (usuario_id,))
        carteiras_lista = cursor.fetchall()
        resumo = obter_resumo_carteiras(cursor, usuario_id)

    return render_template(
        'financas/carteiras.html',
        carteiras=carteiras_lista,
        resumo_carteiras=resumo,
        tipos_carteira=TIPOS_CARTEIRA,
        cores_sugeridas=CORES_CATEGORIA_SUGERIDAS,
        cor_padrao='#0d6efd',
    )


@financas_bp.route('/carteiras/editar/<int:id>', methods=['POST'])
def editar_carteira(id):
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()
    nome = (request.form.get('nome') or '').strip()
    tipo = tipo_carteira_valido(request.form.get('tipo') or 'outro')
    saldo_atual = parse_money(request.form.get('saldo_atual'))
    cor_hex = normalizar_cor_categoria(request.form.get('cor_hex') or '#0d6efd')
    ativa = 1 if request.form.get('ativa') == '1' else 0

    if not nome:
        flash('Informe o nome da carteira.', 'danger')
        return redirect(url_for('financas.carteiras'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE FIN_Carteiras
            SET Nome = ?, Tipo = ?, SaldoAtual = ?, CorHex = ?, Ativa = ?,
                DataAtualizacao = SYSUTCDATETIME()
            WHERE CarteiraId = ? AND UsuarioId = ?
        """, (nome[:100], tipo, saldo_atual, cor_hex, ativa, id, usuario_id))

        if cursor.rowcount == 0:
            flash('Carteira nao encontrada.', 'warning')
            return redirect(url_for('financas.carteiras'))

        sincronizar_caixa_com_carteiras(cursor, usuario_id, mes_atual, ano_atual)

    flash('Carteira atualizada.', 'success')
    return redirect(url_for('financas.carteiras'))


@financas_bp.route('/carteiras/excluir/<int:id>', methods=['POST'])
def excluir_carteira(id):
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT CarteiraId
            FROM FIN_Carteiras
            WHERE CarteiraId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        if not cursor.fetchone():
            flash('Carteira nao encontrada.', 'warning')
            return redirect(url_for('financas.carteiras'))

        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM FIN_Rendas WHERE CarteiraId = ? AND UsuarioId = ?) AS TotalRendas,
                (SELECT COUNT(*) FROM FIN_Lancamentos WHERE CarteiraId = ? AND UsuarioId = ?) AS TotalLancamentos
        """, (id, usuario_id, id, usuario_id))
        uso = cursor.fetchone()
        total_uso = int((uso.TotalRendas or 0) + (uso.TotalLancamentos or 0))

        if total_uso:
            cursor.execute("""
                UPDATE FIN_Carteiras
                SET Ativa = 0, DataAtualizacao = SYSUTCDATETIME()
                WHERE CarteiraId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            flash('Carteira desativada porque ja possui movimentacoes.', 'info')
        else:
            cursor.execute("""
                DELETE FROM FIN_Carteiras
                WHERE CarteiraId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            flash('Carteira excluida.', 'success')

        sincronizar_caixa_com_carteiras(cursor, usuario_id, mes_atual, ano_atual)

    return redirect(url_for('financas.carteiras'))


@financas_bp.route('/categorias', methods=['GET', 'POST'])
def categorias():
    usuario_id = usuario_atual_id()

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        cor_hex = normalizar_cor_categoria(request.form.get('cor_hex'))

        if not nome:
            flash('Informe o nome da categoria.', 'danger')
            return redirect(url_for('financas.categorias'))

        nome = nome[:80]

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT CategoriaId
                FROM FIN_Categorias
                WHERE UsuarioId = ? AND Nome = ?
            """, (usuario_id, nome))
            if cursor.fetchone():
                flash('Voce ja possui uma categoria com esse nome.', 'warning')
                return redirect(url_for('financas.categorias'))

            cursor.execute("""
                INSERT INTO FIN_Categorias (UsuarioId, Nome, CorHex)
                VALUES (?, ?, ?)
            """, (usuario_id, nome, cor_hex))

        flash('Categoria criada com sucesso.', 'success')
        return redirect(url_for('financas.categorias'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                C.CategoriaId,
                C.Nome,
                C.CorHex,
                COUNT(L.LancamentoId) AS TotalLancamentos,
                SUM(CASE WHEN L.Pago = 0 THEN 1 ELSE 0 END) AS Pendentes,
                SUM(CASE WHEN L.Pago = 1 THEN 1 ELSE 0 END) AS Pagos
            FROM FIN_Categorias C
            LEFT JOIN FIN_Lancamentos L
                ON L.CategoriaId = C.CategoriaId
                AND L.UsuarioId = C.UsuarioId
            WHERE C.UsuarioId = ?
            GROUP BY C.CategoriaId, C.Nome, C.CorHex
            ORDER BY C.Nome
        """, (usuario_id,))
        categorias = cursor.fetchall()

    return render_template(
        'financas/categorias.html',
        categorias=categorias,
        cores_sugeridas=CORES_CATEGORIA_SUGERIDAS,
        cor_padrao=COR_CATEGORIA_PADRAO,
    )


@financas_bp.route('/categorias/excluir/<int:id>', methods=['POST'])
def excluir_categoria(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT CategoriaId
            FROM FIN_Categorias
            WHERE CategoriaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        if not cursor.fetchone():
            flash('Categoria nao encontrada.', 'warning')
            return redirect(url_for('financas.categorias'))

        cursor.execute("""
            SELECT COUNT(*)
            FROM FIN_Lancamentos
            WHERE CategoriaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        total_lancamentos = int(cursor.fetchone()[0] or 0)

        if total_lancamentos > 0:
            flash('Esta categoria ja esta em uso e nao pode ser excluida.', 'warning')
            return redirect(url_for('financas.categorias'))

        cursor.execute("""
            DELETE FROM FIN_Categorias
            WHERE CategoriaId = ? AND UsuarioId = ?
        """, (id, usuario_id))

    flash('Categoria excluida.', 'success')
    return redirect(url_for('financas.categorias'))


@financas_bp.route('/rendas/categorias', methods=['GET', 'POST'])
def categorias_rendas():
    usuario_id = usuario_atual_id()

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        cor_hex = normalizar_cor_categoria(request.form.get('cor_hex'))

        if not nome:
            flash('Informe o nome da categoria de renda.', 'danger')
            return redirect(url_for('financas.categorias_rendas'))

        nome = nome[:80]

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT CategoriaRendaId
                FROM FIN_RendaCategorias
                WHERE UsuarioId = ? AND Nome = ?
            """, (usuario_id, nome))
            if cursor.fetchone():
                flash('Voce ja possui uma categoria de renda com esse nome.', 'warning')
                return redirect(url_for('financas.categorias_rendas'))

            cursor.execute("""
                INSERT INTO FIN_RendaCategorias (UsuarioId, Nome, CorHex)
                VALUES (?, ?, ?)
            """, (usuario_id, nome, cor_hex))

        flash('Categoria de renda criada com sucesso.', 'success')
        return redirect(url_for('financas.categorias_rendas'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                C.CategoriaRendaId,
                C.Nome,
                C.CorHex,
                COUNT(R.RendaId) AS TotalRendas,
                SUM(ISNULL(R.ValorPrevisto, 0)) AS TotalPrevisto,
                SUM(ISNULL(R.ValorReal, 0)) AS TotalReal
            FROM FIN_RendaCategorias C
            LEFT JOIN FIN_Rendas R
                ON R.CategoriaRendaId = C.CategoriaRendaId
                AND R.UsuarioId = C.UsuarioId
            WHERE C.UsuarioId = ?
            GROUP BY C.CategoriaRendaId, C.Nome, C.CorHex
            ORDER BY C.Nome
        """, (usuario_id,))
        categorias = cursor.fetchall()

    return render_template(
        'financas/categorias_rendas.html',
        categorias=categorias,
        cores_sugeridas=CORES_CATEGORIA_SUGERIDAS,
        cor_padrao=COR_CATEGORIA_PADRAO,
    )


@financas_bp.route('/rendas/categorias/excluir/<int:id>', methods=['POST'])
def excluir_categoria_renda(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT CategoriaRendaId
            FROM FIN_RendaCategorias
            WHERE CategoriaRendaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        if not cursor.fetchone():
            flash('Categoria de renda nao encontrada.', 'warning')
            return redirect(url_for('financas.categorias_rendas'))

        cursor.execute("""
            SELECT COUNT(*)
            FROM FIN_Rendas
            WHERE CategoriaRendaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        total_rendas = int(cursor.fetchone()[0] or 0)

        if total_rendas > 0:
            flash('Esta categoria ja esta em uso e nao pode ser excluida.', 'warning')
            return redirect(url_for('financas.categorias_rendas'))

        cursor.execute("""
            DELETE FROM FIN_RendaCategorias
            WHERE CategoriaRendaId = ? AND UsuarioId = ?
        """, (id, usuario_id))

    flash('Categoria de renda excluida.', 'success')
    return redirect(url_for('financas.categorias_rendas'))


@financas_bp.route('/rendas/recorrentes', methods=['GET', 'POST'])
def rendas_recorrentes():
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()

    if request.method == 'POST':
        dados, erro = ler_dados_renda_recorrente_form()
        if erro:
            flash(erro, 'danger')
            return redirect(url_for('financas.rendas_recorrentes'))

        with get_db_cursor() as cursor:
            if dados['categoria_renda_id']:
                cursor.execute("""
                    SELECT CategoriaRendaId
                    FROM FIN_RendaCategorias
                    WHERE CategoriaRendaId = ? AND UsuarioId = ?
                """, (dados['categoria_renda_id'], usuario_id))
                if not cursor.fetchone():
                    flash('Selecione uma categoria de renda valida.', 'danger')
                    return redirect(url_for('financas.rendas_recorrentes'))

            if not carteira_ativa_existe(cursor, usuario_id, dados['carteira_id']):
                dados['carteira_id'] = None

            cursor.execute("""
                INSERT INTO FIN_RendasRecorrentes
                (UsuarioId, CategoriaRendaId, CarteiraId, Descricao, ValorPrevisto,
                 DiaRecebimento, Periodicidade, IntervaloMeses, DataInicio, DataFim, Ativa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usuario_id,
                dados['categoria_renda_id'],
                dados['carteira_id'],
                dados['descricao'],
                dados['valor_previsto'],
                dados['dia_recebimento'],
                dados['periodicidade'],
                dados['intervalo_meses'],
                dados['data_inicio'],
                dados['data_fim'],
                dados['ativa'],
            ))
            cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
            renda_recorrente_id = int(cursor.fetchone()[0])

            if dados['ativa']:
                sincronizar_renda_recorrente_primeiro_periodo(cursor, usuario_id, renda_recorrente_id)
                sincronizar_rendas_recorrentes_periodo(cursor, usuario_id, mes_atual, ano_atual, renda_recorrente_id)

        flash('Renda recorrente criada com sucesso.', 'success')
        return redirect(url_for('financas.rendas_recorrentes'))

    with get_db_cursor() as cursor:
        sincronizar_rendas_recorrentes_periodo(cursor, usuario_id, mes_atual, ano_atual)

        cursor.execute("""
            SELECT
                RR.RendaRecorrenteId, RR.CategoriaRendaId, RR.CarteiraId,
                RR.Descricao, RR.ValorPrevisto, RR.DiaRecebimento,
                RR.Periodicidade, RR.IntervaloMeses, RR.DataInicio, RR.DataFim,
                RR.Ativa, RR.DataAtualizacao,
                C.Nome AS CategoriaNome, C.CorHex AS CategoriaCorHex,
                W.Nome AS CarteiraNome, W.CorHex AS CarteiraCorHex,
                ISNULL(O.TotalOcorrencias, 0) AS TotalOcorrencias,
                ISNULL(O.Recebidas, 0) AS Recebidas
            FROM FIN_RendasRecorrentes RR
            LEFT JOIN FIN_RendaCategorias C
                ON C.CategoriaRendaId = RR.CategoriaRendaId
                AND C.UsuarioId = RR.UsuarioId
            LEFT JOIN FIN_Carteiras W
                ON W.CarteiraId = RR.CarteiraId
                AND W.UsuarioId = RR.UsuarioId
            OUTER APPLY (
                SELECT
                    COUNT(*) AS TotalOcorrencias,
                    SUM(CASE WHEN ISNULL(R.ValorReal, 0) > 0 THEN 1 ELSE 0 END) AS Recebidas
                FROM FIN_RendaRecorrenteOcorrencias O
                LEFT JOIN FIN_Rendas R
                    ON R.RendaId = O.RendaId
                    AND R.UsuarioId = O.UsuarioId
                WHERE O.UsuarioId = RR.UsuarioId
                  AND O.RendaRecorrenteId = RR.RendaRecorrenteId
            ) O
            WHERE RR.UsuarioId = ?
            ORDER BY RR.Ativa DESC, RR.Descricao ASC
        """, (usuario_id,))
        recorrentes_rows = cursor.fetchall()

        cursor.execute("""
            SELECT CategoriaRendaId, Nome, CorHex
            FROM FIN_RendaCategorias
            WHERE UsuarioId = ?
            ORDER BY Nome
        """, (usuario_id,))
        categorias_renda = cursor.fetchall()

        carteiras = listar_carteiras_ativas(cursor, usuario_id)

    chave_atual = chave_periodo(mes_atual, ano_atual)
    recorrentes = []
    for row in recorrentes_rows:
        proxima_data = None
        for offset in range(0, 37):
            mes_ref, ano_ref = periodo_por_chave(chave_atual + offset)
            candidata = data_recebimento_recorrente(row, mes_ref, ano_ref)
            if candidata and candidata >= datetime.now(ZoneInfo('America/Sao_Paulo')).date():
                proxima_data = candidata
                break

        recorrentes.append({
            'RendaRecorrenteId': row.RendaRecorrenteId,
            'CategoriaRendaId': row.CategoriaRendaId,
            'CarteiraId': row.CarteiraId,
            'Descricao': row.Descricao,
            'ValorPrevisto': float(row.ValorPrevisto or 0),
            'DiaRecebimento': row.DiaRecebimento,
            'Periodicidade': row.Periodicidade,
            'IntervaloMeses': int(row.IntervaloMeses or 1),
            'PeriodicidadeLabel': rotulo_periodicidade_renda(row.Periodicidade, row.IntervaloMeses),
            'DataInicio': normalizar_data(row.DataInicio),
            'DataFim': normalizar_data(row.DataFim),
            'Ativa': bool(row.Ativa),
            'CategoriaNome': row.CategoriaNome,
            'CategoriaCorHex': row.CategoriaCorHex,
            'CarteiraNome': row.CarteiraNome,
            'CarteiraCorHex': row.CarteiraCorHex,
            'TotalOcorrencias': int(row.TotalOcorrencias or 0),
            'Recebidas': int(row.Recebidas or 0),
            'ProximaData': proxima_data,
        })

    return render_template(
        'financas/rendas_recorrentes.html',
        recorrentes=recorrentes,
        categorias_renda=categorias_renda,
        carteiras=carteiras,
        periodicidades=PERIODICIDADES_RENDA,
        cor_padrao=COR_CATEGORIA_PADRAO,
    )


@financas_bp.route('/rendas/recorrentes/editar/<int:id>', methods=['POST'])
def editar_renda_recorrente(id):
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()
    dados, erro = ler_dados_renda_recorrente_form()

    if erro:
        flash(erro, 'danger')
        return redirect(url_for('financas.rendas_recorrentes'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT RendaRecorrenteId
            FROM FIN_RendasRecorrentes
            WHERE RendaRecorrenteId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        if not cursor.fetchone():
            flash('Renda recorrente nao encontrada.', 'warning')
            return redirect(url_for('financas.rendas_recorrentes'))

        if dados['categoria_renda_id']:
            cursor.execute("""
                SELECT CategoriaRendaId
                FROM FIN_RendaCategorias
                WHERE CategoriaRendaId = ? AND UsuarioId = ?
            """, (dados['categoria_renda_id'], usuario_id))
            if not cursor.fetchone():
                flash('Selecione uma categoria de renda valida.', 'danger')
                return redirect(url_for('financas.rendas_recorrentes'))

        if not carteira_ativa_existe(cursor, usuario_id, dados['carteira_id']):
            dados['carteira_id'] = None

        remover_ocorrencias_renda_recorrente_pendentes(cursor, usuario_id, id)
        cursor.execute("""
            UPDATE FIN_RendasRecorrentes
            SET CategoriaRendaId = ?, CarteiraId = ?, Descricao = ?, ValorPrevisto = ?,
                DiaRecebimento = ?, Periodicidade = ?, IntervaloMeses = ?,
                DataInicio = ?, DataFim = ?, Ativa = ?, DataAtualizacao = SYSUTCDATETIME()
            WHERE RendaRecorrenteId = ? AND UsuarioId = ?
        """, (
            dados['categoria_renda_id'],
            dados['carteira_id'],
            dados['descricao'],
            dados['valor_previsto'],
            dados['dia_recebimento'],
            dados['periodicidade'],
            dados['intervalo_meses'],
            dados['data_inicio'],
            dados['data_fim'],
            dados['ativa'],
            id,
            usuario_id,
        ))

        if dados['ativa']:
            sincronizar_renda_recorrente_primeiro_periodo(cursor, usuario_id, id)
            sincronizar_rendas_recorrentes_periodo(cursor, usuario_id, mes_atual, ano_atual, id)

    flash('Renda recorrente atualizada.', 'success')
    return redirect(url_for('financas.rendas_recorrentes'))


@financas_bp.route('/rendas/recorrentes/excluir/<int:id>', methods=['POST'])
def excluir_renda_recorrente(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT RendaRecorrenteId
            FROM FIN_RendasRecorrentes
            WHERE RendaRecorrenteId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        if not cursor.fetchone():
            flash('Renda recorrente nao encontrada.', 'warning')
            return redirect(url_for('financas.rendas_recorrentes'))

        recebidas = total_ocorrencias_renda_recorrente_recebidas(cursor, usuario_id, id)
        remover_ocorrencias_renda_recorrente_pendentes(cursor, usuario_id, id)

        if recebidas:
            cursor.execute("""
                UPDATE FIN_RendasRecorrentes
                SET Ativa = 0, DataAtualizacao = SYSUTCDATETIME()
                WHERE RendaRecorrenteId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            flash('Renda recorrente desativada para preservar historico recebido.', 'info')
        else:
            cursor.execute("""
                DELETE FROM FIN_RendaRecorrenteOcorrencias
                WHERE RendaRecorrenteId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            cursor.execute("""
                DELETE FROM FIN_RendasRecorrentes
                WHERE RendaRecorrenteId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            flash('Renda recorrente excluida.', 'success')

    return redirect(url_for('financas.rendas_recorrentes'))


@financas_bp.route('/lancamentos/recorrentes', methods=['GET', 'POST'])
def lancamentos_recorrentes():
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()

    if request.method == 'POST':
        dados, erro = ler_dados_lancamento_recorrente_form()
        if erro:
            flash(erro, 'danger')
            return redirect(url_for('financas.lancamentos_recorrentes'))

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT CategoriaId
                FROM FIN_Categorias
                WHERE CategoriaId = ? AND UsuarioId = ?
            """, (dados['categoria_id'], usuario_id))
            if not cursor.fetchone():
                flash('Selecione uma categoria valida.', 'danger')
                return redirect(url_for('financas.lancamentos_recorrentes'))

            cursor.execute("""
                INSERT INTO FIN_LancamentosRecorrentes
                (UsuarioId, CategoriaId, Descricao, ValorEstimado, DiaVencimento,
                 Periodicidade, IntervaloMeses, DataInicio, DataFim, Ativa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usuario_id,
                dados['categoria_id'],
                dados['descricao'],
                dados['valor_estimado'],
                dados['dia_vencimento'],
                dados['periodicidade'],
                dados['intervalo_meses'],
                dados['data_inicio'],
                dados['data_fim'],
                dados['ativa'],
            ))
            cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
            lancamento_recorrente_id = int(cursor.fetchone()[0])

            if dados['ativa']:
                sincronizar_lancamento_recorrente_primeiro_periodo(cursor, usuario_id, lancamento_recorrente_id)
                sincronizar_lancamentos_recorrentes_periodo(cursor, usuario_id, mes_atual, ano_atual, lancamento_recorrente_id)

        flash('Despesa recorrente criada com sucesso.', 'success')
        return redirect(url_for('financas.lancamentos_recorrentes'))

    with get_db_cursor() as cursor:
        sincronizar_lancamentos_recorrentes_periodo(cursor, usuario_id, mes_atual, ano_atual)

        cursor.execute("""
            SELECT
                LR.LancamentoRecorrenteId, LR.CategoriaId,
                LR.Descricao, LR.ValorEstimado, LR.DiaVencimento,
                LR.Periodicidade, LR.IntervaloMeses, LR.DataInicio, LR.DataFim,
                LR.Ativa, LR.DataAtualizacao,
                C.Nome AS CategoriaNome, C.CorHex AS CategoriaCorHex,
                ISNULL(O.TotalOcorrencias, 0) AS TotalOcorrencias,
                ISNULL(O.Pagas, 0) AS Pagas
            FROM FIN_LancamentosRecorrentes LR
            LEFT JOIN FIN_Categorias C
                ON C.CategoriaId = LR.CategoriaId
                AND C.UsuarioId = LR.UsuarioId
            OUTER APPLY (
                SELECT
                    COUNT(*) AS TotalOcorrencias,
                    SUM(CASE WHEN L.Pago = 1 THEN 1 ELSE 0 END) AS Pagas
                FROM FIN_LancamentoRecorrenteOcorrencias O
                LEFT JOIN FIN_Lancamentos L
                    ON L.LancamentoId = O.LancamentoId
                    AND L.UsuarioId = O.UsuarioId
                WHERE O.UsuarioId = LR.UsuarioId
                  AND O.LancamentoRecorrenteId = LR.LancamentoRecorrenteId
            ) O
            WHERE LR.UsuarioId = ?
            ORDER BY LR.Ativa DESC, LR.Descricao ASC
        """, (usuario_id,))
        recorrentes_rows = cursor.fetchall()

        cursor.execute("""
            SELECT CategoriaId, Nome, CorHex
            FROM FIN_Categorias
            WHERE UsuarioId = ?
            ORDER BY Nome
        """, (usuario_id,))
        categorias = cursor.fetchall()

    chave_atual = chave_periodo(mes_atual, ano_atual)
    recorrentes = []
    for row in recorrentes_rows:
        proxima_data = None
        for offset in range(0, 37):
            mes_ref, ano_ref = periodo_por_chave(chave_atual + offset)
            candidata = data_vencimento_recorrente(row, mes_ref, ano_ref)
            if candidata and candidata >= datetime.now(ZoneInfo('America/Sao_Paulo')).date():
                proxima_data = candidata
                break

        recorrentes.append({
            'LancamentoRecorrenteId': row.LancamentoRecorrenteId,
            'CategoriaId': row.CategoriaId,
            'Descricao': row.Descricao,
            'ValorEstimado': float(row.ValorEstimado or 0),
            'DiaVencimento': row.DiaVencimento,
            'Periodicidade': row.Periodicidade,
            'IntervaloMeses': int(row.IntervaloMeses or 1),
            'PeriodicidadeLabel': rotulo_periodicidade_renda(row.Periodicidade, row.IntervaloMeses),
            'DataInicio': normalizar_data(row.DataInicio),
            'DataFim': normalizar_data(row.DataFim),
            'Ativa': bool(row.Ativa),
            'CategoriaNome': row.CategoriaNome,
            'CategoriaCorHex': row.CategoriaCorHex,
            'TotalOcorrencias': int(row.TotalOcorrencias or 0),
            'Pagas': int(row.Pagas or 0),
            'ProximaData': proxima_data,
        })

    return render_template(
        'financas/lancamentos_recorrentes.html',
        recorrentes=recorrentes,
        categorias=categorias,
        periodicidades=PERIODICIDADES_RENDA,
        cor_padrao=COR_CATEGORIA_PADRAO,
    )


@financas_bp.route('/lancamentos/recorrentes/editar/<int:id>', methods=['POST'])
def editar_lancamento_recorrente(id):
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()
    dados, erro = ler_dados_lancamento_recorrente_form()

    if erro:
        flash(erro, 'danger')
        return redirect(url_for('financas.lancamentos_recorrentes'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT LancamentoRecorrenteId
            FROM FIN_LancamentosRecorrentes
            WHERE LancamentoRecorrenteId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        if not cursor.fetchone():
            flash('Despesa recorrente nao encontrada.', 'warning')
            return redirect(url_for('financas.lancamentos_recorrentes'))

        cursor.execute("""
            SELECT CategoriaId
            FROM FIN_Categorias
            WHERE CategoriaId = ? AND UsuarioId = ?
        """, (dados['categoria_id'], usuario_id))
        if not cursor.fetchone():
            flash('Selecione uma categoria valida.', 'danger')
            return redirect(url_for('financas.lancamentos_recorrentes'))

        remover_ocorrencias_lancamento_recorrente_pendentes(cursor, usuario_id, id)
        cursor.execute("""
            UPDATE FIN_LancamentosRecorrentes
            SET CategoriaId = ?, Descricao = ?, ValorEstimado = ?,
                DiaVencimento = ?, Periodicidade = ?, IntervaloMeses = ?,
                DataInicio = ?, DataFim = ?, Ativa = ?, DataAtualizacao = SYSUTCDATETIME()
            WHERE LancamentoRecorrenteId = ? AND UsuarioId = ?
        """, (
            dados['categoria_id'],
            dados['descricao'],
            dados['valor_estimado'],
            dados['dia_vencimento'],
            dados['periodicidade'],
            dados['intervalo_meses'],
            dados['data_inicio'],
            dados['data_fim'],
            dados['ativa'],
            id,
            usuario_id,
        ))

        if dados['ativa']:
            sincronizar_lancamento_recorrente_primeiro_periodo(cursor, usuario_id, id)
            sincronizar_lancamentos_recorrentes_periodo(cursor, usuario_id, mes_atual, ano_atual, id)

    flash('Despesa recorrente atualizada.', 'success')
    return redirect(url_for('financas.lancamentos_recorrentes'))


@financas_bp.route('/lancamentos/recorrentes/excluir/<int:id>', methods=['POST'])
def excluir_lancamento_recorrente(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT LancamentoRecorrenteId
            FROM FIN_LancamentosRecorrentes
            WHERE LancamentoRecorrenteId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        if not cursor.fetchone():
            flash('Despesa recorrente nao encontrada.', 'warning')
            return redirect(url_for('financas.lancamentos_recorrentes'))

        pagas = total_ocorrencias_lancamento_recorrente_pagas(cursor, usuario_id, id)
        remover_ocorrencias_lancamento_recorrente_pendentes(cursor, usuario_id, id)

        if pagas:
            cursor.execute("""
                UPDATE FIN_LancamentosRecorrentes
                SET Ativa = 0, DataAtualizacao = SYSUTCDATETIME()
                WHERE LancamentoRecorrenteId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            flash('Despesa recorrente desativada para preservar historico pago.', 'info')
        else:
            cursor.execute("""
                DELETE FROM FIN_LancamentoRecorrenteOcorrencias
                WHERE LancamentoRecorrenteId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            cursor.execute("""
                DELETE FROM FIN_LancamentosRecorrentes
                WHERE LancamentoRecorrenteId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            flash('Despesa recorrente excluida.', 'success')

    return redirect(url_for('financas.lancamentos_recorrentes'))


@financas_bp.route('/adicionar-gasto', methods=['GET', 'POST'])
def adicionar_gasto():
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()
    mes_sel, ano_sel = normalizar_periodo(
        request.values.get('mes', mes_atual, type=int),
        request.values.get('ano', ano_atual, type=int)
    )

    if request.method == 'POST':
        descricao = (request.form.get('descricao') or '').strip()
        categoria_id = request.form.get('categoria_id')
        valor_est = parse_money(request.form.get('valor_estimado'))
        data_venc = request.form.get('data_vencimento')

        try:
            dt = datetime.strptime(data_venc, '%Y-%m-%d')
        except (TypeError, ValueError):
            flash('Informe uma data de vencimento válida.', 'danger')
            return redirect(url_for('financas.adicionar_gasto', mes=mes_sel, ano=ano_sel))

        mes = dt.month
        ano = dt.year

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT CategoriaId
                FROM FIN_Categorias
                WHERE CategoriaId = ? AND UsuarioId = ?
            """, (categoria_id, usuario_id))
            if not cursor.fetchone():
                flash('Selecione uma categoria valida.', 'danger')
                return redirect(url_for('financas.adicionar_gasto', mes=mes_sel, ano=ano_sel))

            cursor.execute("""
                INSERT INTO FIN_Lancamentos
                (UsuarioId, CategoriaId, Descricao, ValorEstimado, DataVencimento, MesReferencia, AnoReferencia, Pago)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (usuario_id, categoria_id, descricao, valor_est, data_venc, mes, ano))

        flash('Gasto adicionado com sucesso!', 'success')
        return redirect(url_for('financas.dashboard', mes=mes_sel, ano=ano_sel))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT CategoriaId, Nome
            FROM FIN_Categorias
            WHERE UsuarioId = ?
            ORDER BY Nome
        """, (usuario_id,))
        categorias = cursor.fetchall()

    return render_template('financas/form_gasto.html',
                           categorias=categorias, mes=mes_sel, ano=ano_sel)

@financas_bp.route('/dashboard')
@financas_bp.route('', strict_slashes=False)
def dashboard():
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()
    mes_sel, ano_sel = normalizar_periodo(
        request.args.get('mes', mes_atual, type=int),
        request.args.get('ano', ano_atual, type=int)
    )
    mes_anterior, ano_anterior = periodo_anterior(mes_sel, ano_sel)
    mes_proximo, ano_proximo = periodo_proximo(mes_sel, ano_sel)
    anos_lista = sorted({ano_atual - 1, ano_atual, ano_sel - 1, ano_sel, ano_sel + 1})

    with get_db_cursor() as cursor:
        sincronizar_assinaturas_periodo(cursor, usuario_id, mes_sel, ano_sel)
        sincronizar_rendas_recorrentes_periodo(cursor, usuario_id, mes_sel, ano_sel)
        sincronizar_lancamentos_recorrentes_periodo(cursor, usuario_id, mes_sel, ano_sel)
        usuarios_financeiro = usuarios_visiveis_financeiro(cursor, usuario_id) or [usuario_id]
        usuarios_placeholders = placeholders_sql(usuarios_financeiro)

        resumo_params = []
        resumo_params.extend(usuarios_financeiro)
        resumo_params.extend([mes_sel, ano_sel])
        resumo_params.extend(usuarios_financeiro)
        resumo_params.extend([mes_sel, ano_sel])
        resumo_params.extend(usuarios_financeiro)
        resumo_params.extend([mes_sel, ano_sel])
        resumo_params.extend(usuarios_financeiro)
        resumo_params.extend([mes_sel, ano_sel])
        resumo_params.extend(usuarios_financeiro)
        resumo_params.extend([ano_sel, ano_sel, mes_sel])
        resumo_params.extend(usuarios_financeiro)
        resumo_params.extend([mes_sel, ano_sel])

        cursor.execute(f"""
            SELECT
                ISNULL((
                    SELECT SUM(ISNULL(ValorReal, 0))
                    FROM FIN_Rendas
                    WHERE UsuarioId IN ({usuarios_placeholders}) AND MesReferencia = ? AND AnoReferencia = ?
                    AND ISNULL(ValorReal, 0) > 0
                ), 0) AS RendasRecebidas,
                ISNULL((
                    SELECT SUM(ISNULL(ValorPrevisto, 0))
                    FROM FIN_Rendas
                    WHERE UsuarioId IN ({usuarios_placeholders}) AND MesReferencia = ? AND AnoReferencia = ?
                    AND ISNULL(ValorReal, 0) <= 0
                ), 0) AS RendasAReceber,
                ISNULL((
                    SELECT SUM(ISNULL(ValorReal, 0))
                    FROM FIN_Lancamentos
                    WHERE UsuarioId IN ({usuarios_placeholders}) AND Pago = 1
                    AND MesReferencia = ? AND AnoReferencia = ?
                ), 0) AS PagasMes,
                ISNULL((
                    SELECT SUM(ISNULL(ValorEstimado, 0))
                    FROM FIN_Lancamentos
                    WHERE UsuarioId IN ({usuarios_placeholders}) AND Pago = 0
                    AND MesReferencia = ? AND AnoReferencia = ?
                ), 0) AS ContasPendentesMes,
                ISNULL((
                    SELECT SUM(ISNULL(ValorReal, 0))
                    FROM FIN_Lancamentos
                    WHERE UsuarioId IN ({usuarios_placeholders}) AND Pago = 1
                    AND (AnoReferencia < ? OR (AnoReferencia = ? AND MesReferencia <= ?))
                ), 0) AS PagasAcumuladas,
                ISNULL((
                    SELECT SUM(ISNULL(SaldoAtual, 0))
                    FROM FIN_Caixa
                    WHERE UsuarioId IN ({usuarios_placeholders}) AND MesReferencia = ? AND AnoReferencia = ?
                ), 0) AS SaldoBancario
        """, tuple(resumo_params))
        resumo_mes = cursor.fetchone()
        rendas_recebidas = float(resumo_mes.RendasRecebidas or 0)
        rendas_a_receber = float(resumo_mes.RendasAReceber or 0)
        rendas_previstas = rendas_recebidas + rendas_a_receber
        pagas_mes = float(resumo_mes.PagasMes or 0)
        contas_pendentes_mes = float(resumo_mes.ContasPendentesMes or 0)
        pagas_acumuladas = float(resumo_mes.PagasAcumuladas or 0)
        saldo_bancario = float(resumo_mes.SaldoBancario or 0)
        carteiras = listar_carteiras_ativas(cursor, usuario_id)
        resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)

        if len(usuarios_financeiro) == 1 and resumo_carteiras['ativas'] > 0 and mes_sel == mes_atual and ano_sel == ano_atual:
            saldo_bancario = resumo_carteiras['saldo_total']
            sincronizar_caixa_com_carteiras(cursor, usuario_id, mes_sel, ano_sel)

        cursor.execute(f"""
            SELECT L.*, C.Nome as CategoriaNome, C.CorHex,
                   W.Nome AS CarteiraNome, W.CorHex AS CarteiraCorHex
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            LEFT JOIN FIN_Carteiras W
                ON W.CarteiraId = L.CarteiraId
                AND W.UsuarioId = L.UsuarioId
            WHERE L.UsuarioId IN ({usuarios_placeholders}) AND L.MesReferencia = ? AND L.AnoReferencia = ?
            ORDER BY L.DataVencimento ASC
        """, tuple(usuarios_financeiro) + (mes_sel, ano_sel))
        lancamentos = cursor.fetchall()

        saldo_transportado = saldo_transportado_periodo(
            cursor,
            usuario_id,
            mes_sel,
            ano_sel,
            usuarios_ids=usuarios_financeiro,
        )
        fluxo_caixa = montar_fluxo_caixa_diario(
            cursor,
            usuario_id,
            mes_sel,
            ano_sel,
            saldo_bancario + saldo_transportado,
            usuarios_ids=usuarios_financeiro,
        )

        cursor.execute(f"""
            SELECT TOP 6 
                AnoReferencia, 
                MesReferencia,
                SUM(ISNULL(ValorReal, 0)) as TotalGasto
            FROM FIN_Lancamentos
            WHERE UsuarioId IN ({usuarios_placeholders}) AND Pago = 1
            GROUP BY AnoReferencia, MesReferencia
            ORDER BY AnoReferencia DESC, MesReferencia DESC
        """, tuple(usuarios_financeiro))
        historico_gastos = cursor.fetchall()

        historico_gastos.reverse()

        labels_evolucao = [f"{NOMES_MESES.get(d.MesReferencia, d.MesReferencia)[:3]}/{d.AnoReferencia}" for d in historico_gastos]
        valores_evolucao = [float(d.TotalGasto or 0) for d in historico_gastos]

        cursor.execute(f"""
            SELECT 
                C.Nome, 
                SUM(ISNULL(L.ValorReal, 0)) as Total,
                C.CorHex
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId IN ({usuarios_placeholders}) AND L.MesReferencia = ? AND L.AnoReferencia = ? AND L.Pago = 1
            GROUP BY C.Nome, C.CorHex
            ORDER BY Total DESC
        """, tuple(usuarios_financeiro) + (mes_sel, ano_sel))
        ranking_categorias = cursor.fetchall()

        cursor.execute("""
            SELECT CategoriaId, Nome
            FROM FIN_Categorias
            WHERE UsuarioId = ?
            ORDER BY Nome
        """, (usuario_id,))
        categorias = cursor.fetchall()

        resumo_assinaturas = montar_resumo_assinaturas(
            cursor,
            usuario_id,
            usuarios_ids=usuarios_financeiro,
        )
        resumo_metas = montar_resumo_metas(
            cursor,
            usuario_id,
            usuarios_ids=usuarios_financeiro,
        )

    ranking_categorias = [
        {
            'Nome': item.Nome,
            'Total': float(item.Total or 0),
            'CorHex': item.CorHex or '#6c757d',
        }
        for item in ranking_categorias
    ]

    caixa_disponivel = saldo_bancario + saldo_transportado
    saldo_em_caixa_real = caixa_disponivel + rendas_a_receber
    sobra_prevista = saldo_em_caixa_real - contas_pendentes_mes

    labels_grafico = [d['Nome'] for d in ranking_categorias]
    valores_grafico = [d['Total'] for d in ranking_categorias]
    cores_grafico = [d['CorHex'] for d in ranking_categorias]
    ultimo_dia_mes = calendar.monthrange(ano_sel, mes_sel)[1]
    data_padrao_lancamento = date(
        ano_sel,
        mes_sel,
        min(datetime.now(ZoneInfo('America/Sao_Paulo')).day, ultimo_dia_mes)
    ).strftime('%Y-%m-%d')

    return render_template('financas/dashboard.html',
                           meses=MESES_LISTA,
                           anos=anos_lista,
                           mes_sel=mes_sel,
                           ano_sel=ano_sel,
                           nome_mes_sel=NOMES_MESES.get(mes_sel, mes_sel),
                           mes_anterior=mes_anterior,
                           ano_anterior=ano_anterior,
                           mes_proximo=mes_proximo,
                           ano_proximo=ano_proximo,
                           renda=rendas_recebidas,
                           rendas_previstas=rendas_previstas,
                           rendas_a_receber=rendas_a_receber,
                           pagas=pagas_acumuladas,
                           pendentes=contas_pendentes_mes,
                           sobra=sobra_prevista,
                           pagas_mes=pagas_mes,
                           lancamentos=lancamentos,
                           labels_grafico=labels_grafico,
                           valores_grafico=valores_grafico,
                           cores_grafico=cores_grafico,
                           saldo_bancario=saldo_bancario,
                           saldo_transportado=saldo_transportado,
                           saldo_em_caixa=saldo_em_caixa_real,
                           fluxo_caixa=fluxo_caixa,
                           resumo_assinaturas=resumo_assinaturas,
                           resumo_metas=resumo_metas,
                           carteiras=carteiras,
                           resumo_carteiras=resumo_carteiras,
                           labels_evolucao=labels_evolucao,
                           valores_evolucao=valores_evolucao,
                           ranking_categorias=ranking_categorias,
                           categorias=categorias,
                           data_padrao_lancamento=data_padrao_lancamento)

@financas_bp.route('/baixar-gasto/<int:id>', methods=['POST'])
def baixar_gasto(id):
    usuario_id = usuario_atual_id()
    destino = destino_local_ou('financas.dashboard')
    dados = request.get_json(silent=True) or {}
    carteira_id = request.form.get('carteira_id') or dados.get('carteira_id') or None

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ValorEstimado, ISNULL(ValorReal, 0) AS ValorReal, Pago, CarteiraId, MesReferencia, AnoReferencia
            FROM FIN_Lancamentos
            WHERE LancamentoId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        gasto = cursor.fetchone()

        if gasto:
            valor_estimado = float(gasto.ValorEstimado or 0)
            valor_real_atual = float(gasto.ValorReal or 0)
            valor_para_baixa = valor_real_atual if valor_real_atual > 0 else valor_estimado
            carteira_baixa = gasto.CarteiraId if gasto.Pago else carteira_id

            resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)
            if not gasto.Pago and valor_para_baixa > 0 and resumo_carteiras['ativas'] > 0:
                if not carteira_ativa_existe(cursor, usuario_id, carteira_baixa):
                    if request.form.get('next') or request.args.get('next'):
                        flash('Selecione a carteira usada no pagamento.', 'warning')
                        return redirect(destino)
                    return {"success": False, "message": "Selecione a carteira usada no pagamento."}, 400
            elif not carteira_ativa_existe(cursor, usuario_id, carteira_baixa):
                carteira_baixa = None

            cursor.execute("""
                UPDATE FIN_Lancamentos
                SET Pago = 1, ValorReal = ?, CarteiraId = ?
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (valor_para_baixa, carteira_baixa, id, usuario_id))

            if not gasto.Pago and valor_para_baixa > 0:
                movimentar_carteira(cursor, usuario_id, carteira_baixa, -valor_para_baixa)
                ajustar_caixa(cursor, usuario_id, gasto.MesReferencia, gasto.AnoReferencia, -valor_para_baixa)

            if request.form.get('next') or request.args.get('next'):
                flash('Lancamento baixado com sucesso.', 'success')
                return redirect(destino)
            return {"success": True}, 200

    if request.form.get('next') or request.args.get('next'):
        flash('Lancamento nao encontrado.', 'warning')
        return redirect(destino)
    return {"success": False}, 400

@financas_bp.route('/atualizar-valor-estimado/<int:id>', methods=['POST'])
def atualizar_valor_estimado(id):
    usuario_id = usuario_atual_id()
    dados = request.get_json() or {}
    valor_bruto = dados.get('valor', '0')

    try:
        valor_float = parse_money(valor_bruto)
        if valor_float < 0:
            return {"success": False, "message": "Informe um valor estimado maior ou igual a zero."}, 400

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT Pago
                FROM FIN_Lancamentos
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            gasto = cursor.fetchone()

            if not gasto:
                return {"success": False, "message": "Lancamento nao encontrado"}, 404

            if gasto.Pago:
                return {"success": False, "message": "O valor estimado so pode ser editado enquanto o lancamento estiver pendente."}, 409

            cursor.execute("""
                UPDATE FIN_Lancamentos
                SET ValorEstimado = ?
                WHERE LancamentoId = ? AND UsuarioId = ? AND Pago = 0
            """, (valor_float, id, usuario_id))

        return {"success": True}, 200
    except ValueError:
        return {"success": False, "message": "Valor invalido"}, 400

@financas_bp.route('/atualizar-valor-real/<int:id>', methods=['POST'])
def atualizar_valor_real(id):
    usuario_id = usuario_atual_id()
    dados = request.get_json() or {}
    valor_bruto = dados.get('valor', '0')
    carteira_id = dados.get('carteira_id')

    try:
        valor_float = parse_money(valor_bruto)
        if valor_float < 0:
            return {"success": False, "message": "Informe um valor real maior ou igual a zero."}, 400

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT ISNULL(ValorReal, 0) AS ValorReal, Pago, CarteiraId, MesReferencia, AnoReferencia
                FROM FIN_Lancamentos
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            gasto = cursor.fetchone()

            if not gasto:
                return {"success": False, "message": "Lançamento não encontrado"}, 404

            valor_real_anterior = float(gasto.ValorReal or 0) if gasto.Pago else 0.0
            pago = 1 if valor_float > 0 else 0
            diferenca_caixa = valor_real_anterior - valor_float
            carteira_anterior = gasto.CarteiraId
            carteira_nova = carteira_id if carteira_id is not None else carteira_anterior

            if carteira_nova and not carteira_ativa_existe(cursor, usuario_id, carteira_nova):
                return {"success": False, "message": "Carteira invalida."}, 400

            if not pago:
                carteira_nova = None

            cursor.execute("""
                UPDATE FIN_Lancamentos
                SET ValorReal = ?, Pago = ?, CarteiraId = ?
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (valor_float, pago, carteira_nova, id, usuario_id))

            if carteira_anterior == carteira_nova:
                movimentar_carteira(cursor, usuario_id, carteira_nova, diferenca_caixa)
            else:
                movimentar_carteira(cursor, usuario_id, carteira_anterior, valor_real_anterior)
                movimentar_carteira(cursor, usuario_id, carteira_nova, -valor_float)

            # Ao informar o valor real no dashboard, abate o gasto do caixa.
            # Se o valor for editado depois, movimenta apenas a diferença para evitar duplicidade.
            ajustar_caixa(cursor, usuario_id, gasto.MesReferencia, gasto.AnoReferencia, diferenca_caixa)

        return {"success": True, "delta_caixa": diferenca_caixa}, 200
    except ValueError:
        return {"success": False, "message": "Valor inválido"}, 400


@financas_bp.route('/editar-gasto/<int:id>', methods=['POST'])
def editar_gasto(id):
    usuario_id = usuario_atual_id()
    dados = request.get_json(silent=True) or request.form

    descricao = (dados.get('descricao') or '').strip()
    categoria_id = dados.get('categoria_id')
    data_vencimento_bruta = dados.get('data_vencimento')
    pago = str(dados.get('pago', '')).lower() in {'1', 'true', 'on', 'sim', 'pago'}
    recorrente = str(dados.get('recorrente', '')).lower() in {'1', 'true', 'on', 'sim'}
    carteira_id = dados.get('carteira_id') or None

    if not descricao:
        return {"success": False, "message": "Informe a descricao do lancamento."}, 400

    try:
        categoria_id = int(categoria_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "Selecione uma categoria valida."}, 400

    try:
        data_vencimento = datetime.strptime(data_vencimento_bruta, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return {"success": False, "message": "Informe uma data de vencimento valida."}, 400

    try:
        valor_estimado = parse_money_strict(dados.get('valor_estimado'))
        valor_real = parse_money_strict(dados.get('valor_real')) if pago else 0.0
    except (TypeError, ValueError):
        return {"success": False, "message": "Informe valores validos."}, 400

    if valor_estimado < 0:
        return {"success": False, "message": "O valor estimado nao pode ser negativo."}, 400

    if pago and valor_real <= 0:
        return {"success": False, "message": "Informe um valor real maior que zero para marcar como pago."}, 400

    if valor_real < 0:
        return {"success": False, "message": "O valor real nao pode ser negativo."}, 400

    if carteira_id:
        try:
            carteira_id = int(carteira_id)
        except (TypeError, ValueError):
            return {"success": False, "message": "Carteira invalida."}, 400

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ISNULL(ValorReal, 0) AS ValorReal, Pago, CarteiraId, MesReferencia, AnoReferencia
            FROM FIN_Lancamentos
            WHERE LancamentoId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        gasto = cursor.fetchone()

        if not gasto:
            return {"success": False, "message": "Lancamento nao encontrado."}, 404

        cursor.execute("""
            SELECT CategoriaId
            FROM FIN_Categorias
            WHERE CategoriaId = ? AND UsuarioId = ?
        """, (categoria_id, usuario_id))
        if not cursor.fetchone():
            return {"success": False, "message": "Selecione uma categoria valida."}, 400

        resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)
        if pago and valor_real > 0 and resumo_carteiras['ativas'] > 0:
            if not carteira_ativa_existe(cursor, usuario_id, carteira_id):
                return {"success": False, "message": "Selecione uma carteira valida para o pagamento."}, 400
        elif not carteira_ativa_existe(cursor, usuario_id, carteira_id):
            carteira_id = None

        mes_referencia = data_vencimento.month
        ano_referencia = data_vencimento.year

        valor_real_anterior = float(gasto.ValorReal or 0) if gasto.Pago else 0.0
        carteira_anterior = gasto.CarteiraId if gasto.Pago else None
        valor_real_novo = valor_real if pago else 0.0
        carteira_nova = carteira_id if pago else None

        cursor.execute("""
            UPDATE FIN_Lancamentos
            SET CategoriaId = ?,
                Descricao = ?,
                ValorEstimado = ?,
                ValorReal = ?,
                DataVencimento = ?,
                MesReferencia = ?,
                AnoReferencia = ?,
                Pago = ?,
                CarteiraId = ?
            WHERE LancamentoId = ? AND UsuarioId = ?
        """, (
            categoria_id,
            descricao,
            valor_estimado,
            valor_real_novo,
            data_vencimento,
            mes_referencia,
            ano_referencia,
            1 if pago else 0,
            carteira_nova,
            id,
            usuario_id,
        ))

        if gasto.Pago and valor_real_anterior > 0:
            movimentar_carteira(cursor, usuario_id, carteira_anterior, valor_real_anterior)
            ajustar_caixa(cursor, usuario_id, gasto.MesReferencia, gasto.AnoReferencia, valor_real_anterior)

        if pago and valor_real_novo > 0:
            movimentar_carteira(cursor, usuario_id, carteira_nova, -valor_real_novo)
            ajustar_caixa(cursor, usuario_id, mes_referencia, ano_referencia, -valor_real_novo)

        if recorrente:
            criar_regra_recorrente_a_partir_lancamento(cursor, usuario_id, id, {
                'categoria_id': categoria_id,
                'descricao': descricao,
                'valor_estimado': valor_estimado,
                'data_vencimento': data_vencimento,
            })

        ignorar_sincronizacao_assinatura_lancamento(cursor, usuario_id, id)

    return {"success": True}, 200


@financas_bp.route('/rendas', methods=['GET', 'POST'])
def gerenciar_rendas():
    usuario_id = usuario_atual_id()
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))

    # Captura mês/ano da URL ou usa o atual como padrão
    mes = request.args.get('mes', hoje.month, type=int)
    ano = request.args.get('ano', hoje.year, type=int)

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        categoria_renda_id = request.form.get('categoria_renda_id') or None
        carteira_id = request.form.get('carteira_id') or None
        v_previsto = request.form.get('valor_previsto', '0')
        v_real = request.form.get('valor_real', '0')
        data_receb = request.form.get('data_recebimento')
        recorrente = request.form.get('recorrente') == 'on'
        periodicidade_recorrente = periodicidade_renda_valida(
            request.form.get('periodicidade_recorrente') or 'mensal'
        )
        intervalo_recorrente = intervalo_renda(
            periodicidade_recorrente,
            request.form.get('intervalo_recorrente')
        )

        # Converte string vazia ou inválida para 0.0 e evita erro de conversão no SQL Server.
        valor_previsto = parse_money(v_previsto)
        valor_real = parse_money(v_real)

        data_receb = request.form.get('data_recebimento')
        try:
            dt = datetime.strptime(data_receb, '%Y-%m-%d')
        except (TypeError, ValueError):
            flash('Informe uma data de recebimento valida.', 'danger')
            return redirect(url_for('financas.gerenciar_rendas', mes=mes, ano=ano))

        with get_db_cursor() as cursor:
            if categoria_renda_id:
                cursor.execute("""
                    SELECT CategoriaRendaId
                    FROM FIN_RendaCategorias
                    WHERE CategoriaRendaId = ? AND UsuarioId = ?
                """, (categoria_renda_id, usuario_id))
                if not cursor.fetchone():
                    flash('Selecione uma categoria de renda valida.', 'danger')
                    return redirect(url_for('financas.gerenciar_rendas', mes=mes, ano=ano))

            resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)
            if valor_real > 0 and resumo_carteiras['ativas'] > 0:
                if not carteira_ativa_existe(cursor, usuario_id, carteira_id):
                    flash('Selecione a carteira onde a renda caiu.', 'danger')
                    return redirect(url_for('financas.gerenciar_rendas', mes=mes, ano=ano))
            elif not carteira_ativa_existe(cursor, usuario_id, carteira_id):
                carteira_id = None

            renda_recorrente_id = None
            if recorrente:
                cursor.execute("""
                    INSERT INTO FIN_RendasRecorrentes
                    (UsuarioId, CategoriaRendaId, CarteiraId, Descricao, ValorPrevisto,
                     DiaRecebimento, Periodicidade, IntervaloMeses, DataInicio, DataFim, Ativa)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)
                """, (
                    usuario_id,
                    categoria_renda_id,
                    carteira_id,
                    descricao,
                    valor_previsto,
                    dt.day,
                    periodicidade_recorrente,
                    intervalo_recorrente,
                    dt.date(),
                ))
                cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
                renda_recorrente_id = int(cursor.fetchone()[0])

            cursor.execute("""
                INSERT INTO FIN_Rendas
                (UsuarioId, CategoriaRendaId, CarteiraId, RendaRecorrenteId, Descricao,
                 ValorPrevisto, ValorReal, DataRecebimento, MesReferencia, AnoReferencia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usuario_id,
                categoria_renda_id,
                carteira_id,
                renda_recorrente_id,
                descricao,
                valor_previsto,
                valor_real,
                data_receb,
                dt.month,
                dt.year,
            ))
            cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
            renda_id = int(cursor.fetchone()[0])

            if renda_recorrente_id:
                cursor.execute("""
                    INSERT INTO FIN_RendaRecorrenteOcorrencias
                    (UsuarioId, RendaRecorrenteId, RendaId, MesReferencia, AnoReferencia)
                    VALUES (?, ?, ?, ?, ?)
                """, (usuario_id, renda_recorrente_id, renda_id, dt.month, dt.year))

            if valor_real > 0:
                if carteira_id:
                    movimentar_carteira(cursor, usuario_id, carteira_id, valor_real)
                ajustar_caixa(cursor, usuario_id, dt.month, dt.year, valor_real)

        flash('Renda recorrente criada com sucesso!' if recorrente else 'Renda registrada com sucesso!', 'success')
        return redirect(url_for('financas.gerenciar_rendas', mes=dt.month, ano=dt.year))

    with get_db_cursor() as cursor:
        sincronizar_rendas_recorrentes_periodo(cursor, usuario_id, mes, ano)
        cursor.execute("""
            SELECT R.*, C.Nome AS CategoriaNome, C.CorHex AS CategoriaCorHex,
                   W.Nome AS CarteiraNome, W.CorHex AS CarteiraCorHex,
                   RR.Periodicidade AS RecorrenciaPeriodicidade,
                   RR.IntervaloMeses AS RecorrenciaIntervaloMeses
            FROM FIN_Rendas R
            LEFT JOIN FIN_RendaCategorias C
                ON C.CategoriaRendaId = R.CategoriaRendaId
                AND C.UsuarioId = R.UsuarioId
            LEFT JOIN FIN_Carteiras W
                ON W.CarteiraId = R.CarteiraId
                AND W.UsuarioId = R.UsuarioId
            LEFT JOIN FIN_RendasRecorrentes RR
                ON RR.RendaRecorrenteId = R.RendaRecorrenteId
                AND RR.UsuarioId = R.UsuarioId
            WHERE R.UsuarioId = ? AND R.MesReferencia = ? AND R.AnoReferencia = ?
            ORDER BY R.DataRecebimento ASC, R.RendaId ASC
        """, (usuario_id, mes, ano))
        rendas_rows = cursor.fetchall()

        cursor.execute("""
            SELECT CategoriaRendaId, Nome, CorHex
            FROM FIN_RendaCategorias
            WHERE UsuarioId = ?
            ORDER BY Nome
        """, (usuario_id,))
        categorias_renda = cursor.fetchall()

        carteiras = listar_carteiras_ativas(cursor, usuario_id)
        resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)

        cursor.execute("""
            SELECT SaldoAtual
            FROM FIN_Caixa
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes, ano))
        res_caixa = cursor.fetchone()
        saldo_atual = float(res_caixa[0]) if res_caixa and res_caixa[0] else 0.0

    rendas = []
    for renda in rendas_rows:
        valor_previsto = float(renda.ValorPrevisto or 0)
        valor_real = float(renda.ValorReal or 0)
        valor_a_receber = max(valor_previsto - valor_real, 0)
        rendas.append({
            'RendaId': renda.RendaId,
            'RendaRecorrenteId': renda.RendaRecorrenteId,
            'Recorrente': bool(renda.RendaRecorrenteId),
            'RecorrenciaLabel': rotulo_periodicidade_renda(
                renda.RecorrenciaPeriodicidade,
                renda.RecorrenciaIntervaloMeses
            ) if renda.RendaRecorrenteId else None,
            'CategoriaRendaId': renda.CategoriaRendaId,
            'CategoriaNome': renda.CategoriaNome,
            'CategoriaCorHex': renda.CategoriaCorHex,
            'CarteiraId': renda.CarteiraId,
            'CarteiraNome': renda.CarteiraNome,
            'CarteiraCorHex': renda.CarteiraCorHex,
            'Descricao': renda.Descricao,
            'ValorPrevisto': valor_previsto,
            'ValorReal': valor_real,
            'ValorAReceber': valor_a_receber,
            'Recebida': valor_a_receber == 0 and valor_previsto > 0,
        })

    return render_template(
        'financas/rendas.html',
        rendas=rendas,
        categorias_renda=categorias_renda,
        carteiras=carteiras,
        resumo_carteiras=resumo_carteiras,
        cor_padrao=COR_CATEGORIA_PADRAO,
        periodicidades_renda=PERIODICIDADES_RENDA,
        mes=mes,
        ano=ano,
        saldo_atual=saldo_atual,
    )

@financas_bp.route('/deletar-renda/<int:id>', methods=['POST'])
def deletar_renda(id):
    usuario_id = usuario_atual_id()
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ISNULL(ValorReal, 0) AS ValorReal, CarteiraId, MesReferencia, AnoReferencia
            FROM FIN_Rendas
            WHERE RendaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        renda = cursor.fetchone()

        if renda and float(renda.ValorReal or 0) > 0:
            valor_real = float(renda.ValorReal or 0)
            movimentar_carteira(cursor, usuario_id, renda.CarteiraId, -valor_real)
            ajustar_caixa(cursor, usuario_id, renda.MesReferencia, renda.AnoReferencia, -valor_real)

        cursor.execute("""
            DELETE FROM FIN_RendaRecorrenteOcorrencias
            WHERE RendaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        cursor.execute("DELETE FROM FIN_Rendas WHERE RendaId = ? AND UsuarioId = ?", (id, usuario_id))
    return {"success": True}, 200

@financas_bp.route('/editar-renda/<int:id>', methods=['POST'])
def editar_renda(id):
    usuario_id = usuario_atual_id()
    dados = request.get_json() or {}

    # Tratamento para garantir que o SQL receba o tipo correto
    try:
        desc = dados.get('descricao')
        categoria_renda_id = dados.get('categoria_renda_id') or None
        carteira_id = dados.get('carteira_id') or None
        v_prev = parse_money(dados.get('valor_previsto'))
        v_real = parse_money(dados.get('valor_real'))

        with get_db_cursor() as cursor:
            if categoria_renda_id:
                cursor.execute("""
                    SELECT CategoriaRendaId
                    FROM FIN_RendaCategorias
                    WHERE CategoriaRendaId = ? AND UsuarioId = ?
                """, (categoria_renda_id, usuario_id))
                if not cursor.fetchone():
                    return {"success": False, "message": "Categoria de renda invalida."}, 400

            cursor.execute("""
                SELECT ISNULL(ValorReal, 0) AS ValorReal, CarteiraId, MesReferencia, AnoReferencia
                FROM FIN_Rendas
                WHERE RendaId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            renda_atual = cursor.fetchone()
            if not renda_atual:
                return {"success": False, "message": "Renda nao encontrada."}, 404

            resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)
            if v_real > 0 and resumo_carteiras['ativas'] > 0:
                if not carteira_ativa_existe(cursor, usuario_id, carteira_id):
                    return {"success": False, "message": "Selecione uma carteira valida."}, 400
            elif not carteira_ativa_existe(cursor, usuario_id, carteira_id):
                carteira_id = None

            valor_real_anterior = float(renda_atual.ValorReal or 0)
            carteira_anterior = renda_atual.CarteiraId
            diferenca_caixa = v_real - valor_real_anterior

            if carteira_anterior == carteira_id:
                movimentar_carteira(cursor, usuario_id, carteira_id, diferenca_caixa)
            else:
                movimentar_carteira(cursor, usuario_id, carteira_anterior, -valor_real_anterior)
                movimentar_carteira(cursor, usuario_id, carteira_id, v_real)

            cursor.execute("""
                UPDATE FIN_Rendas
                SET CategoriaRendaId = ?, CarteiraId = ?, Descricao = ?, ValorPrevisto = ?, ValorReal = ?
                WHERE RendaId = ? AND UsuarioId = ?
            """, (categoria_renda_id, carteira_id, desc, v_prev, v_real, id, usuario_id))

            ajustar_caixa(cursor, usuario_id, renda_atual.MesReferencia, renda_atual.AnoReferencia, diferenca_caixa)
        return {"success": True}, 200
    except Exception as e:
        return {"success": False, "message": str(e)}, 400

@financas_bp.route('/deletar-gasto/<int:id>', methods=['POST'])
def deletar_gasto(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ISNULL(ValorReal, 0) AS ValorReal, Pago, CarteiraId, MesReferencia, AnoReferencia
            FROM FIN_Lancamentos
            WHERE LancamentoId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        gasto = cursor.fetchone()

        if not gasto:
            return {"success": False, "message": "Lancamento nao encontrado."}, 404

        if gasto and gasto.Pago and float(gasto.ValorReal or 0) > 0:
            valor_real = float(gasto.ValorReal or 0)
            movimentar_carteira(cursor, usuario_id, gasto.CarteiraId, valor_real)
            ajustar_caixa(cursor, usuario_id, gasto.MesReferencia, gasto.AnoReferencia, valor_real)

        ignorar_sincronizacao_assinatura_lancamento(cursor, usuario_id, id)
        ignorar_sincronizacao_lancamento_recorrente(cursor, usuario_id, id)
        cursor.execute("DELETE FROM FIN_Lancamentos WHERE LancamentoId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Lançamento excluído com sucesso!', 'success')

    return {"success": True}, 200

@financas_bp.route('/atualizar-saldo', methods=['POST'])
def atualizar_saldo():
    usuario_id = usuario_atual_id()
    # Aceita valores no formato brasileiro antes de gravar no banco.
    novo_saldo = parse_money(request.form.get('saldo_conta', '0'))

    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))

    mes_sel = request.args.get('mes', hoje.month, type=int)
    ano_sel = request.args.get('ano', hoje.year, type=int)

    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE FIN_Caixa
            SET SaldoAtual = ?, DataAtualizacao = GETDATE()
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (novo_saldo, usuario_id, mes_sel, ano_sel))
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO FIN_Caixa (UsuarioId, MesReferencia, AnoReferencia, SaldoAtual, DataAtualizacao)
                VALUES (?, ?, ?, ?, GETDATE())
            """, (usuario_id, mes_sel, ano_sel, novo_saldo))

    flash('Saldo em conta atualizado com sucesso!', 'success')

    return redirect(url_for('financas.gerenciar_rendas', mes=mes_sel, ano=ano_sel))


@financas_bp.route('/receber-renda/<int:id>', methods=['POST'])
def receber_renda(id):
    usuario_id = usuario_atual_id()
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))
    mes_ref = hoje.month
    ano_ref = hoje.year
    carteira_id = request.form.get('carteira_id') or None

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ValorPrevisto, ISNULL(ValorReal, 0) AS ValorReal, MesReferencia, AnoReferencia
            FROM FIN_Rendas
            WHERE RendaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        renda = cursor.fetchone()

        if renda:
            valor_previsto = float(renda.ValorPrevisto or 0)
            valor_real_atual = float(renda.ValorReal or 0)
            valor_a_creditar = valor_previsto if valor_real_atual <= 0 else 0
            mes_ref = renda.MesReferencia
            ano_ref = renda.AnoReferencia
            resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)

            if valor_a_creditar > 0 and resumo_carteiras['ativas'] > 0:
                if not carteira_ativa_existe(cursor, usuario_id, carteira_id):
                    flash('Selecione a carteira onde a renda caiu.', 'warning')
                    return redirect(url_for('financas.gerenciar_rendas', mes=mes_ref, ano=ano_ref))
            elif not carteira_ativa_existe(cursor, usuario_id, carteira_id):
                carteira_id = None

            cursor.execute("""
                UPDATE FIN_Rendas
                SET ValorReal = ValorPrevisto, CarteiraId = ?
                WHERE RendaId = ? AND UsuarioId = ?
            """, (carteira_id, id, usuario_id))

            if valor_a_creditar > 0:
                movimentar_carteira(cursor, usuario_id, carteira_id, valor_a_creditar)
                cursor.execute("""
                    UPDATE FIN_Caixa
                    SET SaldoAtual = ISNULL(SaldoAtual, 0) + ?, DataAtualizacao = GETDATE()
                    WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
                """, (valor_a_creditar, usuario_id, mes_ref, ano_ref))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO FIN_Caixa (UsuarioId, MesReferencia, AnoReferencia, SaldoAtual, DataAtualizacao)
                        VALUES (?, ?, ?, ?, GETDATE())
                    """, (usuario_id, mes_ref, ano_ref, valor_a_creditar))

    flash('Renda marcada como recebida!', 'success')
    return redirect(url_for('financas.gerenciar_rendas', mes=mes_ref, ano=ano_ref))

@financas_bp.route('/reabrir-renda/<int:id>', methods=['POST'])
def reabrir_renda(id):
    usuario_id = usuario_atual_id()
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))
    mes_ref = hoje.month
    ano_ref = hoje.year

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ValorPrevisto, ISNULL(ValorReal, 0) AS ValorReal, CarteiraId, MesReferencia, AnoReferencia
            FROM FIN_Rendas
            WHERE RendaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        renda = cursor.fetchone()

        if renda:
            valor_a_estornar = float(renda.ValorPrevisto or 0) if float(renda.ValorReal or 0) > 0 else 0
            mes_ref = renda.MesReferencia
            ano_ref = renda.AnoReferencia

            cursor.execute("""
                UPDATE FIN_Rendas
                SET ValorReal = 0, CarteiraId = NULL
                WHERE RendaId = ? AND UsuarioId = ?
            """, (id, usuario_id))

            if valor_a_estornar > 0:
                movimentar_carteira(cursor, usuario_id, renda.CarteiraId, -valor_a_estornar)
                cursor.execute("""
                    UPDATE FIN_Caixa
                    SET SaldoAtual = ISNULL(SaldoAtual, 0) - ?, DataAtualizacao = GETDATE()
                    WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
                """, (valor_a_estornar, usuario_id, mes_ref, ano_ref))

    flash('Renda reaberta como pendente.', 'info')
    return redirect(url_for('financas.gerenciar_rendas', mes=mes_ref, ano=ano_ref))

@financas_bp.route('/clonar-mes-anterior', methods=['POST'])
def clonar_mes_anterior():
    usuario_id = usuario_atual_id()
    mes_atual, ano_atual = periodo_atual()
    mes_destino, ano_destino = normalizar_periodo(
        request.form.get('mes', mes_atual, type=int),
        request.form.get('ano', ano_atual, type=int)
    )
    mes_origem, ano_origem = periodo_anterior(mes_destino, ano_destino)

    with get_db_cursor() as cursor:
        sincronizar_lancamentos_recorrentes_periodo(cursor, usuario_id, mes_destino, ano_destino)

        cursor.execute("""
            SELECT L.CategoriaId, L.Descricao, L.ValorEstimado, L.DataVencimento
            FROM FIN_Lancamentos L
            LEFT JOIN FIN_LancamentoRecorrenteOcorrencias O
                ON O.LancamentoId = L.LancamentoId AND O.UsuarioId = L.UsuarioId
            WHERE L.UsuarioId = ? AND L.MesReferencia = ? AND L.AnoReferencia = ?
              AND L.LancamentoRecorrenteId IS NULL
              AND O.OcorrenciaId IS NULL
            ORDER BY L.DataVencimento, L.LancamentoId
        """, (usuario_id, mes_origem, ano_origem))
        
        lancamentos_antigos = cursor.fetchall()

        if not lancamentos_antigos:
            flash(f'Nenhum lancamento avulso encontrado em {mes_origem}/{ano_origem} para copiar.', 'warning')
            return redirect(url_for('financas.dashboard', mes=mes_destino, ano=ano_destino))

        importados = 0
        ignorados = 0
        for item in lancamentos_antigos:
            data_vencimento = data_vencimento_no_destino(item.DataVencimento, mes_destino, ano_destino)
            cursor.execute("""
                SELECT TOP 1 LancamentoId
                FROM FIN_Lancamentos
                WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
                  AND CategoriaId = ? AND Descricao = ?
            """, (usuario_id, mes_destino, ano_destino, item.CategoriaId, item.Descricao))
            if cursor.fetchone():
                ignorados += 1
                continue

            cursor.execute("""
                INSERT INTO FIN_Lancamentos 
                (UsuarioId, CategoriaId, Descricao, ValorEstimado, ValorReal, DataVencimento, MesReferencia, AnoReferencia, Pago)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, 0)
            """, (usuario_id, item.CategoriaId, item.Descricao, item.ValorEstimado, data_vencimento, mes_destino, ano_destino))
            importados += 1

    if importados:
        complemento = f' ({ignorados} ja existiam e foram ignoradas)' if ignorados else ''
        flash(f'{importados} conta(s) avulsa(s) de {mes_origem}/{ano_origem} importada(s) com sucesso.{complemento}', 'success')
    else:
        flash('Nada foi importado: os lancamentos avulsos do mes anterior ja existem no destino.', 'info')
    return redirect(url_for('financas.dashboard', mes=mes_destino, ano=ano_destino))

@financas_bp.route('/importar-planilha', methods=['POST'])
def importar_abril():
    usuario_id = usuario_atual_id()
    mes_ref = 4
    ano_ref = 2026

    data_padrao = '2026-04-10'

    planilha = [
        ("Impostos", "Impostos DIRECTTI", 660.00), # Corrigido pelo contexto
        ("Fixos", "Pix Contador", 300.00),
        ("Reserva", "PE DE MEIA", 0.00),
        ("Financeiro", "NUBANK Cartao", 1463.60),
        ("Financeiro", "Santander", 5131.79),
        ("Fixos", "Tracker 11/48", 2194.39),
        ("Fixos", "Conta Vivo", 64.70),
        ("Fixos", "Conta Tim", 56.99),
        ("Fixos", "AMIL", 166.96),
        ("Fixos", "Taxa Conta de Luz ENEL", 260.15),
        ("Fixos", "Conta Agua", 465.44),
        ("Fixos", "Conta Internet", 151.90),
        ("Fixos", "Luz Solar 23/36", 608.39),
        ("Educação", "Futebol Caua", 150.00),
        ("Educação", "Natação Maria", 190.00),
        ("Educação", "Inglês Caua", 362.95),
        ("Educação", "Inglês Maria", 297.50),
        ("Educação", "Cejan Cauã", 635.00),
        ("Fixos", "IPTU 5/9", 115.58)
    ]

    with get_db_cursor() as cursor:
        for cat_nome, descricao, valor in planilha:

            cursor.execute("SELECT CategoriaId FROM FIN_Categorias WHERE Nome = ? AND UsuarioId = ?", (cat_nome, usuario_id))
            resultado_cat = cursor.fetchone()

            if resultado_cat:
                cat_id = resultado_cat[0]
            else:
                cursor.execute("INSERT INTO FIN_Categorias (UsuarioId, Nome, CorHex) VALUES (?, ?, '#808080')", (usuario_id, cat_nome))
                cursor.execute("SELECT @@IDENTITY")
                cat_id = int(cursor.fetchone()[0])

            cursor.execute("""
                SELECT LancamentoId FROM FIN_Lancamentos
                WHERE UsuarioId = ? AND Descricao = ? AND MesReferencia = ? AND AnoReferencia = ?
            """, (usuario_id, descricao, mes_ref, ano_ref))
            resultado_lanc = cursor.fetchone()

            if resultado_lanc:
                cursor.execute("""
                    UPDATE FIN_Lancamentos
                    SET ValorEstimado = ?, ValorReal = ?, CategoriaId = ?, Pago = 1
                    WHERE LancamentoId = ?
                """, (valor, valor, cat_id, resultado_lanc[0]))
            else:
                cursor.execute("""
                    INSERT INTO FIN_Lancamentos
                    (UsuarioId, CategoriaId, Descricao, ValorEstimado, ValorReal, DataVencimento, MesReferencia, AnoReferencia, Pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, cat_id, descricao, valor, valor, data_padrao, mes_ref, ano_ref, 1))

    flash('Planilha importada com sucesso para Abril!', 'success')
    return redirect(url_for('financas.dashboard', mes=mes_ref, ano=ano_ref))

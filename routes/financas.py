from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db_cursor
from datetime import datetime, date
import calendar
from flask_login import current_user
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

MESES_LISTA = [
    (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
    (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
    (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
]

NOMES_MESES = dict(MESES_LISTA)


def periodo_atual():
    hoje = datetime.now()
    return hoje.month, hoje.year


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


def data_vencimento_no_destino(data_origem, mes_destino, ano_destino):
    dia_origem = getattr(data_origem, 'day', None) or 10
    ultimo_dia = calendar.monthrange(ano_destino, mes_destino)[1]
    dia = min(dia_origem, ultimo_dia)
    return date(ano_destino, mes_destino, dia)


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


def chave_periodo(mes, ano):
    return ano * 12 + mes


def periodo_por_chave(chave):
    ano = (chave - 1) // 12
    mes = chave - (ano * 12)
    return mes, ano


def saldo_transportado_periodo(cursor, usuario_id, mes, ano, profundidade=12):
    if profundidade <= 0:
        return 0.0

    chave_atual = chave_periodo(mes, ano)
    chave_inicio = chave_atual - profundidade
    chave_fim = chave_atual - 1
    mes_inicio, ano_inicio = periodo_por_chave(chave_inicio)
    mes_fim, ano_fim = periodo_por_chave(chave_fim)
    params_periodo = (
        usuario_id,
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

    cursor.execute("""
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
            WHERE UsuarioId = ?
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
            WHERE UsuarioId = ?
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
            WHERE UsuarioId = ? AND Pago = 0
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


@financas_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))

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

        cursor.execute("""
            SELECT
                ISNULL((
                    SELECT SUM(ISNULL(ValorReal, 0))
                    FROM FIN_Rendas
                    WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
                    AND ISNULL(ValorReal, 0) > 0
                ), 0) AS RendasRecebidas,
                ISNULL((
                    SELECT SUM(ISNULL(ValorPrevisto, 0))
                    FROM FIN_Rendas
                    WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
                    AND ISNULL(ValorReal, 0) <= 0
                ), 0) AS RendasAReceber,
                ISNULL((
                    SELECT SUM(ISNULL(ValorReal, 0))
                    FROM FIN_Lancamentos
                    WHERE UsuarioId = ? AND Pago = 1
                    AND MesReferencia = ? AND AnoReferencia = ?
                ), 0) AS PagasMes,
                ISNULL((
                    SELECT SUM(ISNULL(ValorEstimado, 0))
                    FROM FIN_Lancamentos
                    WHERE UsuarioId = ? AND Pago = 0
                    AND MesReferencia = ? AND AnoReferencia = ?
                ), 0) AS ContasPendentesMes,
                ISNULL((
                    SELECT SUM(ISNULL(ValorReal, 0))
                    FROM FIN_Lancamentos
                    WHERE UsuarioId = ? AND Pago = 1
                    AND (AnoReferencia < ? OR (AnoReferencia = ? AND MesReferencia <= ?))
                ), 0) AS PagasAcumuladas,
                ISNULL((
                    SELECT TOP 1 SaldoAtual
                    FROM FIN_Caixa
                    WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
                ), 0) AS SaldoBancario
        """, (
            usuario_id, mes_sel, ano_sel,
            usuario_id, mes_sel, ano_sel,
            usuario_id, mes_sel, ano_sel,
            usuario_id, mes_sel, ano_sel,
            usuario_id, ano_sel, ano_sel, mes_sel,
            usuario_id, mes_sel, ano_sel,
        ))
        resumo_mes = cursor.fetchone()
        rendas_recebidas = float(resumo_mes.RendasRecebidas or 0)
        rendas_a_receber = float(resumo_mes.RendasAReceber or 0)
        rendas_previstas = rendas_recebidas + rendas_a_receber
        pagas_mes = float(resumo_mes.PagasMes or 0)
        contas_pendentes_mes = float(resumo_mes.ContasPendentesMes or 0)
        pagas_acumuladas = float(resumo_mes.PagasAcumuladas or 0)
        saldo_bancario = float(resumo_mes.SaldoBancario or 0)

        cursor.execute("""
            SELECT L.*, C.Nome as CategoriaNome, C.CorHex
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId = ? AND L.MesReferencia = ? AND L.AnoReferencia = ?
            ORDER BY L.DataVencimento ASC
        """, (usuario_id, mes_sel, ano_sel))
        lancamentos = cursor.fetchall()

        saldo_transportado = saldo_transportado_periodo(cursor, usuario_id, mes_sel, ano_sel)

        cursor.execute("""
            SELECT TOP 6 
                AnoReferencia, 
                MesReferencia,
                SUM(ISNULL(ValorReal, 0)) as TotalGasto
            FROM FIN_Lancamentos
            WHERE UsuarioId = ? AND Pago = 1
            GROUP BY AnoReferencia, MesReferencia
            ORDER BY AnoReferencia DESC, MesReferencia DESC
        """, (usuario_id,))
        historico_gastos = cursor.fetchall()

        historico_gastos.reverse()

        labels_evolucao = [f"{NOMES_MESES.get(d.MesReferencia, d.MesReferencia)[:3]}/{d.AnoReferencia}" for d in historico_gastos]
        valores_evolucao = [float(d.TotalGasto or 0) for d in historico_gastos]

        cursor.execute("""
            SELECT 
                C.Nome, 
                SUM(ISNULL(L.ValorReal, 0)) as Total,
                C.CorHex
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId = ? AND L.MesReferencia = ? AND L.AnoReferencia = ? AND L.Pago = 1
            GROUP BY C.Nome, C.CorHex
            ORDER BY Total DESC
        """, (usuario_id, mes_sel, ano_sel))
        ranking_categorias = cursor.fetchall()

        cursor.execute("""
            SELECT CategoriaId, Nome
            FROM FIN_Categorias
            WHERE UsuarioId = ?
            ORDER BY Nome
        """, (usuario_id,))
        categorias = cursor.fetchall()

        resumo_assinaturas = montar_resumo_assinaturas(cursor, usuario_id)
        resumo_metas = montar_resumo_metas(cursor, usuario_id)

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
        min(datetime.now().day, ultimo_dia_mes)
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
                           resumo_assinaturas=resumo_assinaturas,
                           resumo_metas=resumo_metas,
                           labels_evolucao=labels_evolucao,
                           valores_evolucao=valores_evolucao,
                           ranking_categorias=ranking_categorias,
                           categorias=categorias,
                           data_padrao_lancamento=data_padrao_lancamento)

@financas_bp.route('/baixar-gasto/<int:id>', methods=['POST'])
def baixar_gasto(id):
    usuario_id = usuario_atual_id()
    destino = destino_local_ou('financas.dashboard')

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ValorEstimado, ISNULL(ValorReal, 0) AS ValorReal, Pago, MesReferencia, AnoReferencia
            FROM FIN_Lancamentos
            WHERE LancamentoId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        gasto = cursor.fetchone()

        if gasto:
            valor_estimado = float(gasto.ValorEstimado or 0)
            valor_real_atual = float(gasto.ValorReal or 0)
            valor_para_baixa = valor_real_atual if valor_real_atual > 0 else valor_estimado

            cursor.execute("""
                UPDATE FIN_Lancamentos
                SET Pago = 1, ValorReal = ?
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (valor_para_baixa, id, usuario_id))

            if not gasto.Pago and valor_para_baixa > 0:
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

    try:
        valor_float = parse_money(valor_bruto)
        if valor_float < 0:
            return {"success": False, "message": "Informe um valor real maior ou igual a zero."}, 400

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT ISNULL(ValorReal, 0) AS ValorReal, Pago, MesReferencia, AnoReferencia
                FROM FIN_Lancamentos
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            gasto = cursor.fetchone()

            if not gasto:
                return {"success": False, "message": "Lançamento não encontrado"}, 404

            valor_real_anterior = float(gasto.ValorReal or 0) if gasto.Pago else 0.0
            pago = 1 if valor_float > 0 else 0
            diferenca_caixa = valor_real_anterior - valor_float

            cursor.execute("""
                UPDATE FIN_Lancamentos
                SET ValorReal = ?, Pago = ?
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (valor_float, pago, id, usuario_id))

            # Ao informar o valor real no dashboard, abate o gasto do caixa.
            # Se o valor for editado depois, movimenta apenas a diferença para evitar duplicidade.
            ajustar_caixa(cursor, usuario_id, gasto.MesReferencia, gasto.AnoReferencia, diferenca_caixa)

        return {"success": True, "delta_caixa": diferenca_caixa}, 200
    except ValueError:
        return {"success": False, "message": "Valor inválido"}, 400

@financas_bp.route('/rendas', methods=['GET', 'POST'])
def gerenciar_rendas():
    usuario_id = usuario_atual_id()
    hoje = datetime.now()

    # Captura mês/ano da URL ou usa o atual como padrão
    mes = request.args.get('mes', hoje.month, type=int)
    ano = request.args.get('ano', hoje.year, type=int)

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        v_previsto = request.form.get('valor_previsto', '0')
        v_real = request.form.get('valor_real', '0')
        data_receb = request.form.get('data_recebimento')

        # Converte string vazia ou inválida para 0.0 e evita erro de conversão no SQL Server.
        valor_previsto = parse_money(v_previsto)
        valor_real = parse_money(v_real)

        data_receb = request.form.get('data_recebimento')
        dt = datetime.strptime(data_receb, '%Y-%m-%d')

        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO FIN_Rendas
                (UsuarioId, Descricao, ValorPrevisto, ValorReal, DataRecebimento, MesReferencia, AnoReferencia)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (usuario_id, descricao, valor_previsto, valor_real, data_receb, dt.month, dt.year))

        flash('Renda registrada com sucesso!', 'success')
        return redirect(url_for('financas.gerenciar_rendas', mes=dt.month, ano=dt.year))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM FIN_Rendas
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes, ano))
        rendas_rows = cursor.fetchall()

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
            'Descricao': renda.Descricao,
            'ValorPrevisto': valor_previsto,
            'ValorReal': valor_real,
            'ValorAReceber': valor_a_receber,
            'Recebida': valor_a_receber == 0 and valor_previsto > 0,
        })

    return render_template('financas/rendas.html', rendas=rendas, mes=mes, ano=ano, saldo_atual=saldo_atual)

@financas_bp.route('/deletar-renda/<int:id>', methods=['POST'])
def deletar_renda(id):
    usuario_id = usuario_atual_id()
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM FIN_Rendas WHERE RendaId = ? AND UsuarioId = ?", (id, usuario_id))
    return {"success": True}, 200

@financas_bp.route('/editar-renda/<int:id>', methods=['POST'])
def editar_renda(id):
    usuario_id = usuario_atual_id()
    dados = request.get_json()

    # Tratamento para garantir que o SQL receba o tipo correto
    try:
        desc = dados.get('descricao')
        v_prev = parse_money(dados.get('valor_previsto'))
        v_real = parse_money(dados.get('valor_real'))

        with get_db_cursor() as cursor:
            cursor.execute("""
                UPDATE FIN_Rendas
                SET Descricao = ?, ValorPrevisto = ?, ValorReal = ?
                WHERE RendaId = ? AND UsuarioId = ?
            """, (desc, v_prev, v_real, id, usuario_id))
        return {"success": True}, 200
    except Exception as e:
        return {"success": False, "message": str(e)}, 400

@financas_bp.route('/deletar-gasto/<int:id>', methods=['POST'])
def deletar_gasto(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ISNULL(ValorReal, 0) AS ValorReal, Pago, MesReferencia, AnoReferencia
            FROM FIN_Lancamentos
            WHERE LancamentoId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        gasto = cursor.fetchone()

        if gasto and gasto.Pago and float(gasto.ValorReal or 0) > 0:
            ajustar_caixa(cursor, usuario_id, gasto.MesReferencia, gasto.AnoReferencia, float(gasto.ValorReal or 0))

        cursor.execute("DELETE FROM FIN_Lancamentos WHERE LancamentoId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Lançamento excluído com sucesso!', 'success')

    return {"success": True}, 200

@financas_bp.route('/atualizar-saldo', methods=['POST'])
def atualizar_saldo():
    usuario_id = usuario_atual_id()
    # Aceita valores no formato brasileiro antes de gravar no banco.
    novo_saldo = parse_money(request.form.get('saldo_conta', '0'))

    hoje = datetime.now()

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
    hoje = datetime.now()
    mes_ref = hoje.month
    ano_ref = hoje.year

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

            cursor.execute("""
                UPDATE FIN_Rendas
                SET ValorReal = ValorPrevisto
                WHERE RendaId = ? AND UsuarioId = ?
            """, (id, usuario_id))

            if valor_a_creditar > 0:
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
    hoje = datetime.now()
    mes_ref = hoje.month
    ano_ref = hoje.year

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ValorPrevisto, ISNULL(ValorReal, 0) AS ValorReal, MesReferencia, AnoReferencia
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
                SET ValorReal = 0
                WHERE RendaId = ? AND UsuarioId = ?
            """, (id, usuario_id))

            if valor_a_estornar > 0:
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
        cursor.execute("""
            SELECT TOP 1 LancamentoId FROM FIN_Lancamentos 
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_destino, ano_destino))
        
        ja_tem_dados = cursor.fetchone()

        if ja_tem_dados:
            flash(f'O mês {mes_destino}/{ano_destino} já possui lançamentos. Importação cancelada para evitar duplicidade.', 'danger')
            return redirect(url_for('financas.dashboard', mes=mes_destino, ano=ano_destino))

        cursor.execute("""
            SELECT CategoriaId, Descricao, ValorEstimado, DataVencimento
            FROM FIN_Lancamentos 
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
            ORDER BY DataVencimento, LancamentoId
        """, (usuario_id, mes_origem, ano_origem))
        
        lancamentos_antigos = cursor.fetchall()

        if not lancamentos_antigos:
            flash(f'Nenhum lançamento encontrado em {mes_origem}/{ano_origem} para copiar.', 'warning')
            return redirect(url_for('financas.dashboard', mes=mes_destino, ano=ano_destino))

        for item in lancamentos_antigos:
            data_vencimento = data_vencimento_no_destino(item.DataVencimento, mes_destino, ano_destino)
            cursor.execute("""
                INSERT INTO FIN_Lancamentos 
                (UsuarioId, CategoriaId, Descricao, ValorEstimado, ValorReal, DataVencimento, MesReferencia, AnoReferencia, Pago)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, 0)
            """, (usuario_id, item.CategoriaId, item.Descricao, item.ValorEstimado, data_vencimento, mes_destino, ano_destino))

    flash(f'Contas de {mes_origem}/{ano_origem} clonadas com sucesso!', 'success')
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

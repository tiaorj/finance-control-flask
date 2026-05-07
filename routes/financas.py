from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db_cursor
from datetime import datetime

financas_bp = Blueprint('financas', __name__, url_prefix='/financas')

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

@financas_bp.before_request
def exigir_login():
    if 'admin_logado' not in session:
        return redirect(url_for('admin.login'))

@financas_bp.route('/adicionar-gasto', methods=['GET', 'POST'])
def adicionar_gasto():
    # ID fixo por enquanto (atÃ© integrarmos o login)
    usuario_id = 1
    hoje = datetime.now()

    if request.method == 'POST':
        # Captura os campos hidden que enviamos no form
        mes_sel = request.form.get('mes', type=int)
        ano_sel = request.form.get('ano', type=int)
        descricao = request.form.get('descricao')
        categoria_id = request.form.get('categoria_id')
        valor_est = parse_money(request.form.get('valor_estimado'))
        data_venc = request.form.get('data_vencimento')

        # Extrair mÃªs e ano da data de vencimento para facilitar filtros
        dt = datetime.strptime(data_venc, '%Y-%m-%d')
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


    if request.method == 'GET':
        mes_sel = request.args.get('mes', hoje.month, type=int)
        ano_sel = request.args.get('ano', hoje.year, type=int)

    # GET: Busca categorias para preencher o Select do formulÃ¡rio
    with get_db_cursor() as cursor:
        cursor.execute("SELECT CategoriaId, Nome FROM FIN_Categorias WHERE UsuarioId = ?", (usuario_id,))
        categorias = cursor.fetchall()

    return render_template('financas/form_gasto.html',
                           categorias=categorias, mes=mes_sel, ano=ano_sel)

@financas_bp.route('/')
@financas_bp.route('/dashboard')
def dashboard():
    usuario_id = 1
    hoje = datetime.now()

    # Captura mes/ano da URL ou usa o atual como padrÃ£o
    mes_sel = request.args.get('mes', hoje.month, type=int)
    ano_sel = request.args.get('ano', hoje.year, type=int)

    # Listas para os selects do template
    meses_lista = [
        (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'MarÃ§o'), (4, 'Abril'),
        (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
        (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
    ]
    anos_lista = [hoje.year - 1, hoje.year]

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ValorPrevisto, ISNULL(ValorReal, 0) AS ValorReal
            FROM FIN_Rendas
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_sel, ano_sel))
        rendas_mes = cursor.fetchall()

        rendas_recebidas = 0.0
        rendas_a_receber = 0.0
        for renda in rendas_mes:
            valor_previsto = float(renda.ValorPrevisto or 0)
            valor_real = float(renda.ValorReal or 0)
            if valor_real > 0:
                rendas_recebidas += valor_real
            else:
                rendas_a_receber += valor_previsto

        rendas_previstas = rendas_recebidas + rendas_a_receber
        # Contas jÃ¡ pagas no mÃªs (pagas_mes)
        cursor.execute("""
            SELECT SUM(ValorReal) FROM FIN_Lancamentos
            WHERE UsuarioId = ? AND Pago = 1
            AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_sel, ano_sel))
        res_pagas_mes = cursor.fetchone()
        pagas_mes = float(res_pagas_mes[0]) if res_pagas_mes and res_pagas_mes[0] else 0.0

        # Contas a pagar (Pendentes) do mÃªs
        cursor.execute("""
            SELECT SUM(ValorEstimado) FROM FIN_Lancamentos
            WHERE UsuarioId = ? AND Pago = 0
            AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_sel, ano_sel))
        res_pendentes = cursor.fetchone()
        contas_pendentes_mes = float(res_pendentes[0]) if res_pendentes and res_pendentes[0] else 0.0

        # 2. CONTAS PAGAS ACUMULADAS (HistÃ³rico total para o card de pagas)
        cursor.execute("""
            SELECT SUM(ValorReal) FROM FIN_Lancamentos
            WHERE UsuarioId = ? AND Pago = 1
            AND (AnoReferencia < ? OR (AnoReferencia = ? AND MesReferencia <= ?))
        """, (usuario_id, ano_sel, ano_sel, mes_sel))
        res_pagas_total = cursor.fetchone()
        pagas_acumuladas = float(res_pagas_total[0]) if res_pagas_total and res_pagas_total[0] else 0.0

        # 3. LANÃ‡AMENTOS PARA A TABELA (Listagem do mÃªs)
        cursor.execute("""
            SELECT L.*, C.Nome as CategoriaNome, C.CorHex
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId = ? AND L.MesReferencia = ? AND L.AnoReferencia = ?
            ORDER BY L.DataVencimento ASC
        """, (usuario_id, mes_sel, ano_sel))
        lancamentos = cursor.fetchall()

        # 4. DADOS DO GRÃFICO DE PIZZA
        cursor.execute("""
            SELECT C.Nome, SUM(L.ValorReal) as Total, C.CorHex
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId = ? AND L.MesReferencia = ? AND L.AnoReferencia = ? AND L.Pago = 1
            GROUP BY C.Nome, C.CorHex
        """, (usuario_id, mes_sel, ano_sel))
        dados_grafico = cursor.fetchall()

        # 5. DADOS DO SALDO BANCÃRIO
        # Pega o Saldo que vocÃª digitou manualmente
        cursor.execute("""
            SELECT SaldoAtual
            FROM FIN_Caixa
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_sel, ano_sel))
        res_caixa = cursor.fetchone()
        saldo_bancario = float(res_caixa[0]) if res_caixa else 0.0

    # --- CÃLCULOS FINAIS ---

    # SALDO EM CAIXA: Dinheiro no banco + O que falta receber
    saldo_em_caixa_real = saldo_bancario + rendas_a_receber

    # SALDO PREVISTO (SOBRA): regra original do card.
    # O que deve sobrar = saldo bancÃ¡rio + rendas a receber - contas a pagar.
    sobra_prevista = (saldo_bancario + rendas_a_receber) - contas_pendentes_mes

    # FormataÃ§Ã£o para o Chart.js
    labels_grafico = [d.Nome for d in dados_grafico]
    valores_grafico = [float(d.Total) for d in dados_grafico]
    cores_grafico = [d.CorHex for d in dados_grafico]

    return render_template('financas/dashboard.html',
                           meses=meses_lista,
                           anos=anos_lista,
                           mes_sel=mes_sel,
                           ano_sel=ano_sel,
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
                           saldo_em_caixa=saldo_em_caixa_real)

@financas_bp.route('/baixar-gasto/<int:id>', methods=['POST'])
def baixar_gasto(id):
    usuario_id = 1 #

    with get_db_cursor() as cursor:
        # Primeiro, pegamos o valor estimado para preencher o real na hora da baixa
        cursor.execute("SELECT ValorEstimado FROM FIN_Lancamentos WHERE LancamentoId = ? AND UsuarioId = ?", (id, usuario_id))
        gasto = cursor.fetchone()

        if gasto:
            cursor.execute("""
                UPDATE FIN_Lancamentos
                SET Pago = 1, ValorReal = ValorEstimado
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            return {"success": True}, 200 # Retorno JSON para o JavaScript

    return {"success": False}, 400

@financas_bp.route('/atualizar-valor-real/<int:id>', methods=['POST'])
def atualizar_valor_real(id):
    usuario_id = 1
    # Captura o valor enviado pelo JSON
    dados = request.get_json()
    valor_bruto = dados.get('valor', '0')

    try:
        valor_float = parse_money(valor_bruto)
        with get_db_cursor() as cursor:
            cursor.execute("""
                UPDATE FIN_Lancamentos
                SET ValorReal = ?, Pago = CASE WHEN ? > 0 THEN 1 ELSE Pago END
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (valor_float, valor_float, id, usuario_id))

        return {"success": True}, 200
    except ValueError:
        return {"success": False, "message": "Valor invÃ¡lido"}, 400

@financas_bp.route('/rendas', methods=['GET', 'POST'])
def gerenciar_rendas():
    usuario_id = 1
    hoje = datetime.now()

    # Captura mes/ano da URL ou usa o atual como padrÃ£o
    mes = request.args.get('mes', hoje.month, type=int)
    ano = request.args.get('ano', hoje.year, type=int)

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        v_previsto = request.form.get('valor_previsto', '0')
        v_real = request.form.get('valor_real', '0')
        data_receb = request.form.get('data_recebimento')

        # 2. CONVERSÃƒO CRUCIAL: Se a string for vazia ou invÃ¡lida, vira 0.0
        # Isso impede o erro de 'nvarchar to numeric' no SQL Server
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
    usuario_id = 1
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM FIN_Rendas WHERE RendaId = ? AND UsuarioId = ?", (id, usuario_id))
    return {"success": True}, 200

@financas_bp.route('/editar-renda/<int:id>', methods=['POST'])
def editar_renda(id):
    usuario_id = 1
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
    usuario_id = 1

    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM FIN_Lancamentos WHERE LancamentoId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('LanÃ§amento excluÃ­do com sucesso!', 'success')

    return {"success": True}, 200

@financas_bp.route('/atualizar-saldo', methods=['POST'])
def atualizar_saldo():
    usuario_id = 1
    # Pega o valor, troca vÃ­rgula por ponto para o banco aceitar
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
    usuario_id = 1
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
    # Redireciona de volta para a tela de rendas (ajuste o nome da funÃ§Ã£o se necessÃ¡rio)
    return redirect(url_for('financas.gerenciar_rendas', mes=mes_ref, ano=ano_ref))

@financas_bp.route('/reabrir-renda/<int:id>', methods=['POST'])
def reabrir_renda(id):
    usuario_id = 1
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

@financas_bp.route('/importar-planilha', methods=['POST'])
def importar_abril():
    usuario_id = 1
    mes_ref = 5
    ano_ref = 2026

    # Como a planilha nÃ£o tem a data exata, usei o dia 10 como padrÃ£o.
    # VocÃª pode alterar as datas depois pelo seu sistema.
    data_padrao = '2026-04-10'

    # Dados extraÃ­dos da sua imagem (Categoria, DescriÃ§Ã£o, Valor Real)
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
        ("EducaÃ§Ã£o", "Futebol Caua", 150.00),
        ("EducaÃ§Ã£o", "NataÃ§Ã£o Maria", 190.00),
        ("EducaÃ§Ã£o", "Ingles Caua", 362.95),
        ("EducaÃ§Ã£o", "Ingles Maria", 297.50),
        ("EducaÃ§Ã£o", "Cejan CauÃ£", 635.00),
        ("Fixos", "IPTU 5/9", 115.58)
    ]

    with get_db_cursor() as cursor:
        for cat_nome, descricao, valor in planilha:

            # 1. Busca o ID da Categoria (ou cria uma nova se nÃ£o existir)
            cursor.execute("SELECT CategoriaId FROM FIN_Categorias WHERE Nome = ? AND UsuarioId = ?", (cat_nome, usuario_id))
            resultado_cat = cursor.fetchone()

            if resultado_cat:
                cat_id = resultado_cat[0]
            else:
                cursor.execute("INSERT INTO FIN_Categorias (UsuarioId, Nome, CorHex) VALUES (?, ?, '#808080')", (usuario_id, cat_nome))
                # Busca o Ãºltimo ID gerado na sessÃ£o atual
                cursor.execute("SELECT @@IDENTITY")
                cat_id = int(cursor.fetchone()[0])

            # 2. Verifica se o LanÃ§amento jÃ¡ existe neste mÃªs/ano
            cursor.execute("""
                SELECT LancamentoId FROM FIN_Lancamentos
                WHERE UsuarioId = ? AND Descricao = ? AND MesReferencia = ? AND AnoReferencia = ?
            """, (usuario_id, descricao, mes_ref, ano_ref))
            resultado_lanc = cursor.fetchone()

            if resultado_lanc:
                # 3. UPDATE: Se jÃ¡ existe, atualiza os valores e marca como pago
                cursor.execute("""
                    UPDATE FIN_Lancamentos
                    SET ValorEstimado = ?, ValorReal = ?, CategoriaId = ?, Pago = 1
                    WHERE LancamentoId = ?
                """, (valor, valor, cat_id, resultado_lanc[0]))
            else:
                # 4. INSERT: Se nÃ£o existe, cria um novo
                cursor.execute("""
                    INSERT INTO FIN_Lancamentos
                    (UsuarioId, CategoriaId, Descricao, ValorEstimado, ValorReal, DataVencimento, MesReferencia, AnoReferencia, Pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, cat_id, descricao, valor, valor, data_padrao, mes_ref, ano_ref, 0))

    # Redireciona direto para o mÃªs de Abril/2026 para vocÃª ver a mÃ¡gica acontecer
    flash('Planilha importada com sucesso para Abril!', 'success')
    return redirect(url_for('financas.dashboard', mes=5, ano=2026))

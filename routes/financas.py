from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_cursor
from datetime import datetime

financas_bp = Blueprint('financas', __name__, url_prefix='/financas')

@financas_bp.route('/adicionar-gasto', methods=['GET', 'POST'])
def adicionar_gasto():
    # ID fixo por enquanto (até integrarmos o login)
    usuario_id = 1 
    hoje = datetime.now()
  
    if request.method == 'POST':
        # Captura os campos hidden que enviamos no form
        mes_sel = request.form.get('mes', type=int)
        ano_sel = request.form.get('ano', type=int)        
        descricao = request.form.get('descricao')
        categoria_id = request.form.get('categoria_id')
        valor_est = request.form.get('valor_estimado').replace(',', '.')
        data_venc = request.form.get('data_vencimento')
        
        # Extrair mês e ano da data de vencimento para facilitar filtros
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

    # GET: Busca categorias para preencher o Select do formulário
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
    
    # Captura mes/ano da URL ou usa o atual como padrão
    mes_sel = request.args.get('mes', hoje.month, type=int)
    ano_sel = request.args.get('ano', hoje.year, type=int)

    # Listas para os selects do template
    meses_lista = [
        (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
        (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
        (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
    ]
    anos_lista = [hoje.year - 1, hoje.year]

    with get_db_cursor() as cursor:
        # 1. MOVIMENTAÇÃO DO MÊS ATUAL
        # Renda Real do mês
        cursor.execute("""
            SELECT SUM(ValorReal) FROM FIN_Rendas 
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_sel, ano_sel))
        res_renda = cursor.fetchone()
        renda_mes = float(res_renda[0]) if res_renda and res_renda[0] else 0.0

        # Contas já pagas no mês (pagas_mes)
        cursor.execute("""
            SELECT SUM(ValorReal) FROM FIN_Lancamentos 
            WHERE UsuarioId = ? AND Pago = 1 
            AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_sel, ano_sel))
        res_pagas_mes = cursor.fetchone()
        pagas_mes = float(res_pagas_mes[0]) if res_pagas_mes and res_pagas_mes[0] else 0.0

        # Contas a pagar (Pendentes) do mês
        cursor.execute("""
            SELECT SUM(ValorEstimado) FROM FIN_Lancamentos 
            WHERE UsuarioId = ? AND Pago = 0 
            AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes_sel, ano_sel))
        res_pendentes = cursor.fetchone()
        contas_pendentes_mes = float(res_pendentes[0]) if res_pendentes and res_pendentes[0] else 0.0

        # 2. CONTAS PAGAS ACUMULADAS (Histórico total para o card de pagas)
        cursor.execute("""
            SELECT SUM(ValorReal) FROM FIN_Lancamentos 
            WHERE UsuarioId = ? AND Pago = 1
            AND (AnoReferencia < ? OR (AnoReferencia = ? AND MesReferencia <= ?))
        """, (usuario_id, ano_sel, ano_sel, mes_sel))
        res_pagas_total = cursor.fetchone()
        pagas_acumuladas = float(res_pagas_total[0]) if res_pagas_total and res_pagas_total[0] else 0.0

        # 3. LANÇAMENTOS PARA A TABELA (Listagem do mês)
        cursor.execute("""
            SELECT L.*, C.Nome as CategoriaNome, C.CorHex 
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId = ? AND L.MesReferencia = ? AND L.AnoReferencia = ?
            ORDER BY L.DataVencimento ASC
        """, (usuario_id, mes_sel, ano_sel))
        lancamentos = cursor.fetchall()

        # 4. DADOS DO GRÁFICO DE PIZZA
        cursor.execute("""
            SELECT C.Nome, SUM(L.ValorReal) as Total, C.CorHex
            FROM FIN_Lancamentos L
            JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId = ? AND L.MesReferencia = ? AND L.AnoReferencia = ? AND L.Pago = 1
            GROUP BY C.Nome, C.CorHex
        """, (usuario_id, mes_sel, ano_sel))
        dados_grafico = cursor.fetchall()

    # --- LÓGICA DE CÁLCULO SOLICITADA ---
    # Sobra prevista é o faturamento real menos o que já foi pago
    sobra_prevista = renda_mes - pagas_mes

    # Formatação para o Chart.js
    labels_grafico = [d.Nome for d in dados_grafico]
    valores_grafico = [float(d.Total) for d in dados_grafico]
    cores_grafico = [d.CorHex for d in dados_grafico]

    return render_template('financas/dashboard.html', 
                           meses=meses_lista, 
                           anos=anos_lista,
                           mes=mes_sel, 
                           ano=ano_sel,
                           renda=renda_mes,
                           pagas=pagas_acumuladas,
                           saldo_total=renda_mes, # Ajustado conforme o contexto de faturamento do mês
                           pendentes=contas_pendentes_mes,
                           sobra=sobra_prevista,
                           pagas_mes=pagas_mes,
                           lancamentos=lancamentos,
                           labels_grafico=labels_grafico,
                           valores_grafico=valores_grafico,
                           cores_grafico=cores_grafico)

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
        valor_limpo = valor_bruto.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        valor_float = float(valor_limpo)
        with get_db_cursor() as cursor:
            cursor.execute("""
                UPDATE FIN_Lancamentos 
                SET ValorReal = ?, Pago = CASE WHEN ? > 0 THEN 1 ELSE Pago END
                WHERE LancamentoId = ? AND UsuarioId = ?
            """, (valor_float, valor_float, id, usuario_id))
            
        return {"success": True}, 200
    except ValueError:
        return {"success": False, "message": "Valor inválido"}, 400
    
@financas_bp.route('/rendas', methods=['GET', 'POST'])
def gerenciar_rendas():
    usuario_id = 1
    hoje = datetime.now()

    # Captura mes/ano da URL ou usa o atual como padrão
    mes = request.args.get('mes', hoje.month, type=int)
    ano = request.args.get('ano', hoje.year, type=int)

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        v_previsto = request.form.get('valor_previsto', '0').replace(',', '.')
        v_real = request.form.get('valor_real', '0').replace(',', '.')
        data_receb = request.form.get('data_recebimento')
        
        # 2. CONVERSÃO CRUCIAL: Se a string for vazia ou inválida, vira 0.0
        # Isso impede o erro de 'nvarchar to numeric' no SQL Server
        try:
            valor_previsto = float(v_previsto) if v_previsto else 0.0
            valor_real = float(v_real) if v_real else 0.0
        except ValueError:
            valor_previsto = 0.0
            valor_real = 0.0

        data_receb = request.form.get('data_recebimento')
        dt = datetime.strptime(data_receb, '%Y-%m-%d')
        
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO FIN_Rendas 
                (UsuarioId, Descricao, ValorPrevisto, ValorReal, DataRecebimento, MesReferencia, AnoReferencia)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (usuario_id, descricao, valor_previsto, valor_real, data_receb, dt.month, dt.year))
        
        flash('Renda registrada com sucesso!', 'success')
        return redirect(url_for('financas.dashboard'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM FIN_Rendas 
            WHERE UsuarioId = ? AND MesReferencia = ? AND AnoReferencia = ?
        """, (usuario_id, mes, ano))
        rendas = cursor.fetchall()

    return render_template('financas/rendas.html', rendas=rendas, mes=mes, ano=ano)

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
        v_prev = float(dados.get('valor_previsto').replace(',', '.'))
        v_real = float(dados.get('valor_real').replace(',', '.'))
        
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
    
    hoje = datetime.now()

    mes_sel = request.args.get('mes', hoje.month, type=int)
    ano_sel = request.args.get('ano', hoje.year, type=int)

    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM FIN_Lancamentos WHERE LancamentoId = ? AND UsuarioId = ?", (id, usuario_id))
    
    flash('Lançamento excluído com sucesso!', 'success')
    
    return redirect(url_for('financas.dashboard', mes=mes_sel,ano=ano_sel))

@financas_bp.route('/importar-abril')
def importar_abril():
    usuario_id = 1
    mes_ref = 4
    ano_ref = 2026
    
    # Como a planilha não tem a data exata, usei o dia 10 como padrão. 
    # Você pode alterar as datas depois pelo seu sistema.
    data_padrao = '2026-04-10'

    # Dados extraídos da sua imagem (Categoria, Descrição, Valor Real)
    planilha = [
        ("Impostos", "Impostos DIRECTTI", 660.00), # Corrigido pelo contexto
        ("Fixos", "Pix Contador", 300.00),
        ("Reserva", "PE DE MEIA", 0.01),
        ("Financeiro", "NUBANK Cartao", 1081.00),
        ("Financeiro", "Santander", 8470.44),
        ("Fixos", "Tracker 11/48", 2194.39),
        ("Fixos", "Conta Vivo", 64.70),
        ("Fixos", "Conta Tim", 56.99),
        ("Fixos", "AMIL", 166.96),
        ("Fixos", "Taxa Conta de Luz ENEL", 260.15),
        ("Fixos", "Conta Agua", 359.38),
        ("Fixos", "Conta Internet", 151.90),
        ("Fixos", "Luz Solar 23/36", 609.80),
        ("Educação", "Futebol Caua", 0.01),
        ("Educação", "Natação Maria", 190.00),
        ("Educação", "Ingles Caua", 362.95),
        ("Educação", "Ingles Maria", 297.50),
        ("Educação", "Cejan Cauã", 635.00),
        ("Fixos", "Iracema", 500.00),
        ("Extras", "Deposito Crianças", 0.01),
        ("Extras", "Deposito Luana", 0.01),
        ("Fixos", "IPTU 4/9", 115.58),
        ("Extras", "CRA-RJ", 421.84)
    ]

    with get_db_cursor() as cursor:
        for cat_nome, descricao, valor in planilha:
            
            # 1. Busca o ID da Categoria (ou cria uma nova se não existir)
            cursor.execute("SELECT CategoriaId FROM FIN_Categorias WHERE Nome = ? AND UsuarioId = ?", (cat_nome, usuario_id))
            resultado_cat = cursor.fetchone()
            
            if resultado_cat:
                cat_id = resultado_cat[0]
            else:
                cursor.execute("INSERT INTO FIN_Categorias (UsuarioId, Nome, CorHex) VALUES (?, ?, '#808080')", (usuario_id, cat_nome))
                # Busca o último ID gerado na sessão atual
                cursor.execute("SELECT @@IDENTITY")
                cat_id = int(cursor.fetchone()[0])

            # 2. Verifica se o Lançamento já existe neste mês/ano
            cursor.execute("""
                SELECT LancamentoId FROM FIN_Lancamentos 
                WHERE UsuarioId = ? AND Descricao = ? AND MesReferencia = ? AND AnoReferencia = ?
            """, (usuario_id, descricao, mes_ref, ano_ref))
            resultado_lanc = cursor.fetchone()

            if resultado_lanc:
                # 3. UPDATE: Se já existe, atualiza os valores e marca como pago
                cursor.execute("""
                    UPDATE FIN_Lancamentos 
                    SET ValorEstimado = ?, ValorReal = ?, CategoriaId = ?, Pago = 1
                    WHERE LancamentoId = ?
                """, (valor, valor, cat_id, resultado_lanc[0]))
            else:
                # 4. INSERT: Se não existe, cria um novo
                cursor.execute("""
                    INSERT INTO FIN_Lancamentos 
                    (UsuarioId, CategoriaId, Descricao, ValorEstimado, ValorReal, DataVencimento, MesReferencia, AnoReferencia, Pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, cat_id, descricao, valor, valor, data_padrao, mes_ref, ano_ref, 1))

    # Redireciona direto para o mês de Abril/2026 para você ver a mágica acontecer
    flash('Planilha importada com sucesso para Abril!', 'success')
    return redirect(url_for('financas.dashboard', mes=4, ano=2026))
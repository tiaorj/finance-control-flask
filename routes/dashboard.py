from datetime import datetime

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from database import get_db_cursor


dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/admin')


def _perfil_status(cursor):
    checks = [
        ("Experi&ecirc;ncias", "SELECT COUNT(*) FROM ExperienciaProfissional"),
        ("Forma&ccedil;&atilde;o", "SELECT COUNT(*) FROM FormacaoAcademica"),
        ("Projetos", "SELECT COUNT(*) FROM Projeto"),
        ("Certifica&ccedil;&otilde;es", "SELECT COUNT(*) FROM Certificacoes"),
    ]
    concluidos = 0
    detalhes = []

    for label, query in checks:
        cursor.execute(query)
        total = cursor.fetchone()[0]
        ativo = total > 0
        concluidos += 1 if ativo else 0
        detalhes.append({"label": label, "ativo": ativo})

    percentual = int((concluidos / len(checks)) * 100)
    return percentual, detalhes


@dashboard_bp.route('/dashboard')
@login_required
def index():
    usuario_id = int(current_user.get_id())
    hoje = datetime.now()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                ISNULL((
                    SELECT SUM(ISNULL(ValorReal, 0))
                    FROM FIN_Rendas
                    WHERE UsuarioId = ?
                    AND MesReferencia = ?
                    AND AnoReferencia = ?
                    AND ISNULL(ValorReal, 0) > 0
                ), 0) AS RendasRecebidas,
                ISNULL((
                    SELECT SUM(ISNULL(ValorPrevisto, 0))
                    FROM FIN_Rendas
                    WHERE UsuarioId = ?
                    AND MesReferencia = ?
                    AND AnoReferencia = ?
                    AND ISNULL(ValorReal, 0) <= 0
                ), 0) AS RendasAReceber,
                ISNULL((
                    SELECT SUM(ISNULL(ValorEstimado, 0))
                    FROM FIN_Lancamentos
                    WHERE UsuarioId = ?
                    AND MesReferencia = ?
                    AND AnoReferencia = ?
                    AND Pago = 0
                ), 0) AS ContasPendentes,
                ISNULL((
                    SELECT TOP 1 SaldoAtual
                    FROM FIN_Caixa
                    WHERE UsuarioId = ?
                    AND MesReferencia = ?
                    AND AnoReferencia = ?
                ), 0) AS SaldoAtual
        """, (
            usuario_id, hoje.month, hoje.year,
            usuario_id, hoje.month, hoje.year,
            usuario_id, hoje.month, hoje.year,
            usuario_id, hoje.month, hoje.year,
        ))
        financeiro = cursor.fetchone()

        cursor.execute("""
            SELECT TOP 4 L.Descricao, L.ValorEstimado, L.DataVencimento, C.Nome AS CategoriaNome
            FROM FIN_Lancamentos L
            LEFT JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
            WHERE L.UsuarioId = ?
            AND L.Pago = 0
            ORDER BY L.DataVencimento ASC
        """, (usuario_id,))
        proximas_contas = cursor.fetchall()

        perfil_percentual, perfil_itens = _perfil_status(cursor)

    saldo_atual = float(financeiro.SaldoAtual or 0)
    rendas_recebidas = float(financeiro.RendasRecebidas or 0)
    rendas_a_receber = float(financeiro.RendasAReceber or 0)
    contas_pendentes = float(financeiro.ContasPendentes or 0)
    saldo_previsto = saldo_atual + rendas_a_receber - contas_pendentes

    servicos = [
        {
            "titulo": "Upgrade financeiro",
            "texto": "Relat&oacute;rios, indicadores avan&ccedil;ados e acompanhamento mensal.",
            "icone": "bi-graph-up-arrow",
            "url": "main.index",
            "anchor": "#planos",
        },
        {
            "titulo": "Consultoria de curr&iacute;culo",
            "texto": "Revis&atilde;o de posicionamento profissional, curr&iacute;culo e LinkedIn.",
            "icone": "bi-person-vcard",
            "url": "empresa.contato",
            "anchor": "?servico=curriculo",
        },
        {
            "titulo": "Solicitar suporte",
            "texto": "Abra uma demanda para ajustes, d&uacute;vidas ou desenvolvimento sob medida.",
            "icone": "bi-headset",
            "url": "empresa.contato",
            "anchor": "?servico=suporte",
        },
    ]

    artigos = [
        {
            "titulo": "Como separar finan&ccedil;as pessoais e opera&ccedil;&atilde;o",
            "categoria": "Finan&ccedil;as",
            "tempo": "5 min",
        },
        {
            "titulo": "O que um bom perfil profissional precisa mostrar",
            "categoria": "Carreira",
            "tempo": "4 min",
        },
        {
            "titulo": "Quando trocar planilhas por um portal interno",
            "categoria": "Tecnologia",
            "tempo": "6 min",
        },
    ]

    return render_template(
        'admin/dashboard.html',
        mes_atual=hoje.strftime('%m/%Y'),
        saldo_atual=saldo_atual,
        saldo_previsto=saldo_previsto,
        rendas_recebidas=rendas_recebidas,
        rendas_a_receber=rendas_a_receber,
        contas_pendentes=contas_pendentes,
        proximas_contas=proximas_contas,
        perfil_percentual=perfil_percentual,
        perfil_itens=perfil_itens,
        servicos=servicos,
        artigos=artigos,
    )

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from database import get_db_cursor
from helpers.modulos import usuario_tem_modulo
from helpers.sql import placeholders_sql
from helpers.workspaces import usuarios_visiveis_financeiro
from routes.financeiro_integracoes import sincronizar_assinaturas_periodo
from routes.financas import (
    listar_carteiras_ativas,
    obter_resumo_carteiras,
    sincronizar_caixa_com_carteiras,
    sincronizar_rendas_recorrentes_periodo,
)
from routes.tarefas import montar_resumo_tarefas
from routes.veiculos import montar_resumo_veiculos
from routes.garantias import montar_resumo_garantias


dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/admin')


def _perfil_status(cursor, usuario_id):
    checks = [
        ("Experi&ecirc;ncias", "SELECT COUNT(*) FROM ExperienciaProfissional WHERE UsuarioId = ?"),
        ("Forma&ccedil;&atilde;o", "SELECT COUNT(*) FROM FormacaoAcademica WHERE UsuarioId = ?"),
        ("Projetos", "SELECT COUNT(*) FROM Projeto WHERE UsuarioId = ?"),
        ("Certifica&ccedil;&otilde;es", "SELECT COUNT(*) FROM Certificacoes WHERE UsuarioId = ?"),
    ]
    concluidos = 0
    detalhes = []

    for label, query in checks:
        cursor.execute(query, (usuario_id,))
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
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))
    modulo_financeiro = usuario_tem_modulo('finance')
    modulo_life = usuario_tem_modulo('life')
    modulo_carreiras = usuario_tem_modulo('careers')

    saldo_atual = 0.0
    saldo_previsto = 0.0
    rendas_recebidas = 0.0
    rendas_a_receber = 0.0
    contas_pendentes = 0.0
    proximas_contas = []
    perfil_percentual = 0
    perfil_itens = []
    resumo_tarefas = {'proximas': []}
    resumo_veiculos = {'proximos': []}
    resumo_garantias = {'proximas': []}
    carteiras = []
    resumo_carteiras = {'ativas': 0, 'saldo_total': 0.0}

    if modulo_financeiro or modulo_life or modulo_carreiras:
        with get_db_cursor() as cursor:
            if modulo_financeiro:
                sincronizar_assinaturas_periodo(cursor, usuario_id, hoje.month, hoje.year)
                sincronizar_rendas_recorrentes_periodo(cursor, usuario_id, hoje.month, hoje.year)
                usuarios_financeiro = usuarios_visiveis_financeiro(cursor, usuario_id) or [usuario_id]
                usuarios_placeholders = placeholders_sql(usuarios_financeiro)

                financeiro_params = []
                financeiro_params.extend(usuarios_financeiro)
                financeiro_params.extend([hoje.month, hoje.year])
                financeiro_params.extend(usuarios_financeiro)
                financeiro_params.extend([hoje.month, hoje.year])
                financeiro_params.extend(usuarios_financeiro)
                financeiro_params.extend([hoje.month, hoje.year])
                financeiro_params.extend(usuarios_financeiro)
                financeiro_params.extend([hoje.month, hoje.year])

                cursor.execute(f"""
                    SELECT
                        ISNULL((
                            SELECT SUM(ISNULL(ValorReal, 0))
                            FROM FIN_Rendas
                            WHERE UsuarioId IN ({usuarios_placeholders})
                            AND MesReferencia = ?
                            AND AnoReferencia = ?
                            AND ISNULL(ValorReal, 0) > 0
                        ), 0) AS RendasRecebidas,
                        ISNULL((
                            SELECT SUM(ISNULL(ValorPrevisto, 0))
                            FROM FIN_Rendas
                            WHERE UsuarioId IN ({usuarios_placeholders})
                            AND MesReferencia = ?
                            AND AnoReferencia = ?
                            AND ISNULL(ValorReal, 0) <= 0
                        ), 0) AS RendasAReceber,
                        ISNULL((
                            SELECT SUM(ISNULL(ValorEstimado, 0))
                            FROM FIN_Lancamentos
                            WHERE UsuarioId IN ({usuarios_placeholders})
                            AND MesReferencia = ?
                            AND AnoReferencia = ?
                            AND Pago = 0
                        ), 0) AS ContasPendentes,
                        ISNULL((
                            SELECT SUM(ISNULL(SaldoAtual, 0))
                            FROM FIN_Caixa
                            WHERE UsuarioId IN ({usuarios_placeholders})
                            AND MesReferencia = ?
                            AND AnoReferencia = ?
                        ), 0) AS SaldoAtual
                """, tuple(financeiro_params))
                financeiro = cursor.fetchone()
                carteiras = listar_carteiras_ativas(cursor, usuario_id)
                resumo_carteiras = obter_resumo_carteiras(cursor, usuario_id)

                if len(usuarios_financeiro) == 1 and resumo_carteiras['ativas'] > 0:
                    sincronizar_caixa_com_carteiras(cursor, usuario_id, hoje.month, hoje.year)

                cursor.execute(f"""
                    SELECT TOP 4 L.LancamentoId, L.Descricao, L.ValorEstimado, L.DataVencimento, C.Nome AS CategoriaNome
                    FROM FIN_Lancamentos L
                    LEFT JOIN FIN_Categorias C ON L.CategoriaId = C.CategoriaId
                    WHERE L.UsuarioId IN ({usuarios_placeholders})
                    AND L.Pago = 0
                    ORDER BY L.DataVencimento ASC
                """, tuple(usuarios_financeiro))
                proximas_contas = cursor.fetchall()

                saldo_atual = (
                    resumo_carteiras['saldo_total']
                    if len(usuarios_financeiro) == 1 and resumo_carteiras['ativas'] > 0
                    else float(financeiro.SaldoAtual or 0)
                )
                rendas_recebidas = float(financeiro.RendasRecebidas or 0)
                rendas_a_receber = float(financeiro.RendasAReceber or 0)
                contas_pendentes = float(financeiro.ContasPendentes or 0)
                saldo_previsto = saldo_atual + rendas_a_receber - contas_pendentes

            if modulo_carreiras:
                perfil_percentual, perfil_itens = _perfil_status(cursor, usuario_id)

            if modulo_life:
                resumo_tarefas = montar_resumo_tarefas(cursor, usuario_id)
                resumo_veiculos = montar_resumo_veiculos(cursor, usuario_id)
                resumo_garantias = montar_resumo_garantias(cursor, usuario_id)

    servicos = [
        {
            "titulo": "Cofre de garantias",
            "texto": "Notas fiscais, prazos de garantia e bens importantes em um so lugar.",
            "icone": "bi-shield-check",
            "url": "garantias.lista",
            "anchor": "",
        },
        {
            "titulo": "Gestor de ve&iacute;culos",
            "texto": "Manuten&ccedil;&otilde;es, documentos e alertas por data ou quilometragem.",
            "icone": "bi-car-front",
            "url": "veiculos.lista",
            "anchor": "",
        },
        {
            "titulo": "Checklist dom&eacute;stico",
            "texto": "Tarefas recorrentes, documentos e lembretes que voltam no m&ecirc;s certo.",
            "icone": "bi-calendar2-check",
            "url": "tarefas.lista",
            "anchor": "",
        },
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
        modulo_financeiro=modulo_financeiro,
        modulo_life=modulo_life,
        modulo_carreiras=modulo_carreiras,
        mes_atual=hoje.strftime('%m/%Y'),
        saldo_atual=saldo_atual,
        saldo_previsto=saldo_previsto,
        rendas_recebidas=rendas_recebidas,
        rendas_a_receber=rendas_a_receber,
        contas_pendentes=contas_pendentes,
        proximas_contas=proximas_contas,
        perfil_percentual=perfil_percentual,
        perfil_itens=perfil_itens,
        resumo_tarefas=resumo_tarefas,
        resumo_veiculos=resumo_veiculos,
        resumo_garantias=resumo_garantias,
        carteiras=carteiras,
        resumo_carteiras=resumo_carteiras,
        servicos=servicos,
        artigos=artigos,
    )

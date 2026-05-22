from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from database import get_db_cursor
from helpers.sql import placeholders_sql
from routes.financeiro_integracoes import ajustar_caixa, periodo_atual


metas_bp = Blueprint('metas', __name__, url_prefix='/app/metas')
TIPOS_MOVIMENTACAO = {'aporte', 'retirada'}


def usuario_atual_id():
    return int(current_user.get_id())


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


def normalizar_data(valor):
    if isinstance(valor, date):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str) and valor:
        return datetime.strptime(valor[:10], '%Y-%m-%d').date()
    return None


def montar_meta(row):
    valor_alvo = float(row.ValorAlvo or 0)
    valor_atual = float(row.ValorAtual or 0)
    progresso = min((valor_atual / valor_alvo * 100) if valor_alvo > 0 else 0, 100)
    data_alvo = normalizar_data(row.DataAlvo)
    dias_restantes = (data_alvo - datetime.now(ZoneInfo('America/Sao_Paulo')).date()).days if data_alvo else None

    return {
        'id': row.MetaId,
        'nome': row.Nome,
        'valor_alvo': valor_alvo,
        'valor_atual': valor_atual,
        'valor_restante': max(valor_alvo - valor_atual, 0),
        'progresso': progresso,
        'data_alvo': data_alvo,
        'dias_restantes': dias_restantes,
        'cor_hex': row.CorHex or '#0d6efd',
        'ativa': bool(row.Ativa),
        'observacoes': row.Observacoes,
        'concluida': valor_alvo > 0 and valor_atual >= valor_alvo,
    }


def montar_resumo_metas(cursor, usuario_id, usuarios_ids=None):
    usuarios_ids = usuarios_ids or [usuario_id]
    usuarios_placeholders = placeholders_sql(usuarios_ids)

    cursor.execute(f"""
        SELECT MetaId, Nome, ValorAlvo, ValorAtual, DataAlvo, CorHex, Ativa, Observacoes
        FROM FIN_Metas
        WHERE UsuarioId IN ({usuarios_placeholders}) AND Ativa = 1
        ORDER BY
            CASE WHEN ValorAlvo > 0 AND ValorAtual >= ValorAlvo THEN 1 ELSE 0 END,
            DataAlvo ASC,
            Nome ASC
    """, tuple(usuarios_ids))
    metas = [montar_meta(row) for row in cursor.fetchall()]

    total_alvo = sum(meta['valor_alvo'] for meta in metas)
    total_atual = sum(meta['valor_atual'] for meta in metas)

    return {
        'metas': metas,
        'total_alvo': total_alvo,
        'total_atual': total_atual,
        'total_restante': max(total_alvo - total_atual, 0),
        'progresso_geral': min((total_atual / total_alvo * 100) if total_alvo > 0 else 0, 100),
        'ativas': len(metas),
        'concluidas': len([meta for meta in metas if meta['concluida']]),
    }


@metas_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))


@metas_bp.route('/')
def lista():
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        resumo = montar_resumo_metas(cursor, usuario_id)
        cursor.execute("""
            SELECT TOP 8 M.Nome, MM.Tipo, MM.Valor, MM.Observacao, MM.DataMovimentacao
            FROM FIN_MetaMovimentacoes MM
            JOIN FIN_Metas M ON MM.MetaId = M.MetaId
            WHERE MM.UsuarioId = ?
            ORDER BY MM.DataMovimentacao DESC
        """, (usuario_id,))
        movimentacoes = cursor.fetchall()

    return render_template(
        'metas/lista.html',
        metas=resumo['metas'],
        resumo=resumo,
        movimentacoes=movimentacoes,
    )


@metas_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@metas_bp.route('/form/<int:id>', methods=['GET', 'POST'])
def form(id):
    usuario_id = usuario_atual_id()

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        valor_alvo = parse_money(request.form.get('valor_alvo'))
        valor_atual = parse_money(request.form.get('valor_atual'))
        data_alvo = request.form.get('data_alvo') or None
        cor_hex = (request.form.get('cor_hex') or '#0d6efd').strip()
        observacoes = (request.form.get('observacoes') or '').strip() or None
        ativa = 1 if request.form.get('ativa') == 'on' else 0

        if not nome:
            flash('Informe o nome da meta.', 'danger')
            return redirect(url_for('metas.form', id=id) if id else url_for('metas.form'))

        if valor_alvo <= 0:
            flash('Informe um valor alvo maior que zero.', 'danger')
            return redirect(url_for('metas.form', id=id) if id else url_for('metas.form'))

        if valor_atual < 0:
            flash('O valor atual não pode ser negativo.', 'danger')
            return redirect(url_for('metas.form', id=id) if id else url_for('metas.form'))

        if data_alvo:
            try:
                normalizar_data(data_alvo)
            except ValueError:
                flash('Informe uma data alvo válida.', 'danger')
                return redirect(url_for('metas.form', id=id) if id else url_for('metas.form'))

        with get_db_cursor() as cursor:
            mes_ref, ano_ref = periodo_atual()
            if id:
                cursor.execute("""
                    SELECT ValorAtual
                    FROM FIN_Metas
                    WHERE MetaId = ? AND UsuarioId = ?
                """, (id, usuario_id))
                meta_atual = cursor.fetchone()
                if not meta_atual:
                    flash('Meta nÃ£o encontrada.', 'warning')
                    return redirect(url_for('metas.lista'))

                valor_atual_anterior = float(meta_atual.ValorAtual or 0)

                cursor.execute("""
                    UPDATE FIN_Metas
                    SET Nome = ?, ValorAlvo = ?, ValorAtual = ?, DataAlvo = ?, CorHex = ?,
                        Ativa = ?, Observacoes = ?, DataAtualizacao = SYSUTCDATETIME()
                    WHERE MetaId = ? AND UsuarioId = ?
                """, (nome, valor_alvo, valor_atual, data_alvo, cor_hex, ativa, observacoes, id, usuario_id))

                delta_meta = valor_atual - valor_atual_anterior
                if delta_meta:
                    tipo_movimento = 'aporte' if delta_meta > 0 else 'retirada'
                    valor_movimento = abs(delta_meta)
                    ajustar_caixa(cursor, usuario_id, mes_ref, ano_ref, -delta_meta)
                    cursor.execute("""
                        INSERT INTO FIN_MetaMovimentacoes (MetaId, UsuarioId, Tipo, Valor, Observacao)
                        VALUES (?, ?, ?, ?, ?)
                    """, (id, usuario_id, tipo_movimento, valor_movimento, 'Ajuste pelo cadastro da meta'))

                flash('Meta atualizada com sucesso!', 'success')
            else:
                cursor.execute("""
                    INSERT INTO FIN_Metas
                    (UsuarioId, Nome, ValorAlvo, ValorAtual, DataAlvo, CorHex, Ativa, Observacoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, nome, valor_alvo, valor_atual, data_alvo, cor_hex, ativa, observacoes))
                cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
                nova_meta_id = int(cursor.fetchone()[0])

                if valor_atual > 0:
                    ajustar_caixa(cursor, usuario_id, mes_ref, ano_ref, -valor_atual)
                    cursor.execute("""
                        INSERT INTO FIN_MetaMovimentacoes (MetaId, UsuarioId, Tipo, Valor, Observacao)
                        VALUES (?, ?, 'aporte', ?, ?)
                    """, (nova_meta_id, usuario_id, valor_atual, 'Valor inicial reservado na meta'))

                flash('Meta criada com sucesso!', 'success')

        return redirect(url_for('metas.lista'))

    meta = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT MetaId, Nome, ValorAlvo, ValorAtual, DataAlvo, CorHex, Ativa, Observacoes
                FROM FIN_Metas
                WHERE MetaId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            meta = cursor.fetchone()

    return render_template('metas/form.html', meta=meta)


@metas_bp.route('/movimentar/<int:id>', methods=['POST'])
def movimentar(id):
    usuario_id = usuario_atual_id()
    tipo = (request.form.get('tipo') or 'aporte').lower()
    valor = parse_money(request.form.get('valor'))
    observacao = (request.form.get('observacao') or '').strip() or None

    if tipo not in TIPOS_MOVIMENTACAO:
        flash('Tipo de movimentação inválido.', 'danger')
        return redirect(url_for('metas.lista'))

    if valor <= 0:
        flash('Informe um valor maior que zero.', 'danger')
        return redirect(url_for('metas.lista'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ValorAtual
            FROM FIN_Metas
            WHERE MetaId = ? AND UsuarioId = ?
        """, (id, usuario_id))
        meta = cursor.fetchone()

        if not meta:
            flash('Meta não encontrada.', 'warning')
            return redirect(url_for('metas.lista'))

        valor_atual = float(meta.ValorAtual or 0)
        if tipo == 'retirada' and valor_atual <= 0:
            flash('Esta meta nÃ£o possui valor reservado para retirada.', 'warning')
            return redirect(url_for('metas.lista'))

        valor_movimentado = valor if tipo == 'aporte' else min(valor, valor_atual)
        novo_valor = valor_atual + valor_movimentado if tipo == 'aporte' else valor_atual - valor_movimentado

        cursor.execute("""
            UPDATE FIN_Metas
            SET ValorAtual = ?, DataAtualizacao = SYSUTCDATETIME()
            WHERE MetaId = ? AND UsuarioId = ?
        """, (novo_valor, id, usuario_id))

        cursor.execute("""
            INSERT INTO FIN_MetaMovimentacoes (MetaId, UsuarioId, Tipo, Valor, Observacao)
            VALUES (?, ?, ?, ?, ?)
        """, (id, usuario_id, tipo, valor_movimentado, observacao))

        mes_ref, ano_ref = periodo_atual()
        delta_caixa = -valor_movimentado if tipo == 'aporte' else valor_movimentado
        ajustar_caixa(cursor, usuario_id, mes_ref, ano_ref, delta_caixa)

    flash('Meta movimentada com sucesso!', 'success')
    return redirect(url_for('metas.lista'))


@metas_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM FIN_MetaMovimentacoes WHERE MetaId = ? AND UsuarioId = ?", (id, usuario_id))
        cursor.execute("DELETE FROM FIN_Metas WHERE MetaId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Meta removida.', 'warning')
    return redirect(url_for('metas.lista'))

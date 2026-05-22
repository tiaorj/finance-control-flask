from calendar import monthrange
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from database import get_db_cursor


veiculos_bp = Blueprint('veiculos', __name__, url_prefix='/app/veiculos')

TIPOS_VEICULO = ['carro', 'moto', 'utilitario', 'outro']
TIPOS_LEMBRETE = {
    'oleo': 'Troca de oleo',
    'ipva': 'IPVA',
    'seguro': 'Seguro',
    'pneus': 'Pneus',
    'licenciamento': 'Licenciamento',
    'revisao': 'Revisao',
    'outro': 'Outro',
}


def usuario_atual_id():
    return int(current_user.get_id())


def parse_int(valor, default=None):
    if valor is None or str(valor).strip() == '':
        return default

    valor_limpo = str(valor).replace('.', '').replace(',', '').strip()
    try:
        return int(valor_limpo)
    except ValueError:
        return default


def parse_money(valor, default=None):
    if valor is None or str(valor).strip() == '':
        return default

    valor_limpo = str(valor).replace('R$', '').replace(' ', '')
    if ',' in valor_limpo:
        valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
    try:
        return float(valor_limpo)
    except ValueError:
        return default


def normalizar_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor:
        return datetime.strptime(valor[:10], '%Y-%m-%d').date()
    return None


def somar_meses(data_base, meses):
    mes = data_base.month - 1 + meses
    ano = data_base.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data_base.day, monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def status_lembrete(row, hoje=None):
    hoje = hoje or date.today()
    data_vencimento = normalizar_data(row.DataVencimento)
    km_atual = row.QuilometragemAtual
    km_vencimento = row.KmVencimento

    dias = (data_vencimento - hoje).days if data_vencimento else None
    km_restante = (km_vencimento - km_atual) if km_vencimento is not None and km_atual is not None else None
    vencido_por_km = km_restante is not None and km_restante <= 0
    vencido_por_data = dias is not None and dias < 0

    if row.Concluido:
        return 'concluido', 'Concluido', dias, km_restante
    if vencido_por_km or vencido_por_data:
        return 'atrasado', 'Vencido', dias, km_restante
    if dias == 0:
        return 'hoje', 'Vence hoje', dias, km_restante
    if dias is not None and dias <= 30:
        return 'breve', f'Em {dias} dias', dias, km_restante
    if km_restante is not None and km_restante <= 500:
        return 'breve', f'Em {km_restante} km', dias, km_restante

    return 'ok', 'Em dia', dias, km_restante


def montar_lembrete(row, hoje=None):
    status, status_texto, dias, km_restante = status_lembrete(row, hoje)

    return {
        'id': row.LembreteId,
        'veiculo_id': row.VeiculoId,
        'veiculo': row.Apelido,
        'tipo': row.Tipo,
        'tipo_label': TIPOS_LEMBRETE.get(row.Tipo, 'Outro'),
        'titulo': row.Titulo,
        'data_vencimento': normalizar_data(row.DataVencimento),
        'km_vencimento': row.KmVencimento,
        'km_atual': row.QuilometragemAtual,
        'recorrencia_meses': row.RecorrenciaMeses,
        'intervalo_km': row.IntervaloKm,
        'valor_estimado': float(row.ValorEstimado or 0),
        'concluido': bool(row.Concluido),
        'ultima_conclusao': row.UltimaConclusao,
        'observacoes': row.Observacoes,
        'status': status,
        'status_texto': status_texto,
        'dias': dias,
        'km_restante': km_restante,
    }


def montar_resumo_veiculos(cursor, usuario_id, hoje=None):
    hoje = hoje or date.today()

    cursor.execute("""
        SELECT L.LembreteId, L.VeiculoId, V.Apelido, V.QuilometragemAtual,
               L.Tipo, L.Titulo, L.DataVencimento, L.KmVencimento,
               L.RecorrenciaMeses, L.IntervaloKm, L.ValorEstimado,
               L.Concluido, L.UltimaConclusao, L.Observacoes
        FROM APP_VeiculoLembretes L
        JOIN APP_Veiculos V ON L.VeiculoId = V.VeiculoId AND V.UsuarioId = L.UsuarioId
        WHERE L.UsuarioId = ? AND V.Ativo = 1 AND L.Concluido = 0
        ORDER BY
            CASE WHEN L.DataVencimento IS NULL THEN 1 ELSE 0 END,
            L.DataVencimento ASC,
            L.KmVencimento ASC,
            L.Titulo ASC
    """, (usuario_id,))
    lembretes = [montar_lembrete(row, hoje) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT COUNT(*) AS Total
        FROM APP_Veiculos
        WHERE UsuarioId = ? AND Ativo = 1
    """, (usuario_id,))
    total_veiculos = int(cursor.fetchone().Total or 0)

    return {
        'veiculos': total_veiculos,
        'lembretes': lembretes,
        'proximos': lembretes[:5],
        'atrasados': len([item for item in lembretes if item['status'] == 'atrasado']),
        'proximos_30': len([item for item in lembretes if item['dias'] is not None and 0 <= item['dias'] <= 30]),
        'por_km': len([item for item in lembretes if item['km_restante'] is not None and item['km_restante'] <= 500]),
    }


@veiculos_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))


@veiculos_bp.route('/')
def lista():
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        resumo = montar_resumo_veiculos(cursor, usuario_id)
        cursor.execute("""
            SELECT VeiculoId, Apelido, Tipo, Marca, Modelo, Ano, Placa,
                   QuilometragemAtual, Ativo, Observacoes
            FROM APP_Veiculos
            WHERE UsuarioId = ?
            ORDER BY Ativo DESC, Apelido ASC
        """, (usuario_id,))
        veiculos = cursor.fetchall()

        cursor.execute("""
            SELECT L.LembreteId, L.VeiculoId, V.Apelido, V.QuilometragemAtual,
                   L.Tipo, L.Titulo, L.DataVencimento, L.KmVencimento,
                   L.RecorrenciaMeses, L.IntervaloKm, L.ValorEstimado,
                   L.Concluido, L.UltimaConclusao, L.Observacoes
            FROM APP_VeiculoLembretes L
            JOIN APP_Veiculos V ON L.VeiculoId = V.VeiculoId AND V.UsuarioId = L.UsuarioId
            WHERE L.UsuarioId = ?
            ORDER BY L.Concluido ASC, L.DataVencimento ASC, L.KmVencimento ASC, L.Titulo ASC
        """, (usuario_id,))
        lembretes = [montar_lembrete(row) for row in cursor.fetchall()]

    return render_template(
        'veiculos/lista.html',
        veiculos=veiculos,
        lembretes=lembretes,
        resumo=resumo,
    )


@veiculos_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@veiculos_bp.route('/form/<int:id>', methods=['GET', 'POST'])
def form(id):
    usuario_id = usuario_atual_id()

    if request.method == 'POST':
        apelido = (request.form.get('apelido') or '').strip()
        tipo = (request.form.get('tipo') or 'carro').lower()
        marca = (request.form.get('marca') or '').strip() or None
        modelo = (request.form.get('modelo') or '').strip() or None
        ano = parse_int(request.form.get('ano'))
        placa = (request.form.get('placa') or '').strip().upper() or None
        quilometragem = parse_int(request.form.get('quilometragem_atual'))
        observacoes = (request.form.get('observacoes') or '').strip() or None
        ativo = 1 if request.form.get('ativo') == 'on' else 0

        if not apelido:
            flash('Informe um nome para o veiculo.', 'danger')
            return redirect(url_for('veiculos.form', id=id) if id else url_for('veiculos.form'))

        if tipo not in TIPOS_VEICULO:
            flash('Selecione um tipo valido.', 'danger')
            return redirect(url_for('veiculos.form', id=id) if id else url_for('veiculos.form'))

        with get_db_cursor() as cursor:
            if id:
                cursor.execute("""
                    UPDATE APP_Veiculos
                    SET Apelido = ?, Tipo = ?, Marca = ?, Modelo = ?, Ano = ?, Placa = ?,
                        QuilometragemAtual = ?, Ativo = ?, Observacoes = ?,
                        DataAtualizacao = SYSUTCDATETIME()
                    WHERE VeiculoId = ? AND UsuarioId = ?
                """, (apelido, tipo, marca, modelo, ano, placa, quilometragem, ativo, observacoes, id, usuario_id))
                flash('Veiculo atualizado com sucesso.', 'success')
            else:
                cursor.execute("""
                    INSERT INTO APP_Veiculos
                    (UsuarioId, Apelido, Tipo, Marca, Modelo, Ano, Placa, QuilometragemAtual, Ativo, Observacoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, apelido, tipo, marca, modelo, ano, placa, quilometragem, ativo, observacoes))
                flash('Veiculo cadastrado com sucesso.', 'success')

        return redirect(url_for('veiculos.lista'))

    veiculo = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT VeiculoId, Apelido, Tipo, Marca, Modelo, Ano, Placa,
                       QuilometragemAtual, Ativo, Observacoes
                FROM APP_Veiculos
                WHERE VeiculoId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            veiculo = cursor.fetchone()

    return render_template('veiculos/form.html', veiculo=veiculo, tipos=TIPOS_VEICULO)


@veiculos_bp.route('/lembrete/form', defaults={'id': None}, methods=['GET', 'POST'])
@veiculos_bp.route('/lembrete/form/<int:id>', methods=['GET', 'POST'])
def form_lembrete(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT VeiculoId, Apelido
            FROM APP_Veiculos
            WHERE UsuarioId = ? AND Ativo = 1
            ORDER BY Apelido ASC
        """, (usuario_id,))
        veiculos = cursor.fetchall()

    if request.method == 'POST':
        veiculo_id = parse_int(request.form.get('veiculo_id'))
        tipo = (request.form.get('tipo') or 'outro').lower()
        titulo = (request.form.get('titulo') or '').strip()
        data_vencimento = request.form.get('data_vencimento') or None
        km_vencimento = parse_int(request.form.get('km_vencimento'))
        recorrencia_meses = parse_int(request.form.get('recorrencia_meses'))
        intervalo_km = parse_int(request.form.get('intervalo_km'))
        valor_estimado = parse_money(request.form.get('valor_estimado'))
        observacoes = (request.form.get('observacoes') or '').strip() or None
        concluido = 1 if request.form.get('concluido') == 'on' else 0

        if not veiculo_id:
            flash('Selecione um veiculo.', 'danger')
            return redirect(url_for('veiculos.form_lembrete', id=id) if id else url_for('veiculos.form_lembrete'))

        if tipo not in TIPOS_LEMBRETE:
            flash('Selecione um tipo valido.', 'danger')
            return redirect(url_for('veiculos.form_lembrete', id=id) if id else url_for('veiculos.form_lembrete'))

        if not titulo:
            titulo = TIPOS_LEMBRETE[tipo]

        if not data_vencimento and km_vencimento is None:
            flash('Informe uma data ou quilometragem de vencimento.', 'danger')
            return redirect(url_for('veiculos.form_lembrete', id=id) if id else url_for('veiculos.form_lembrete'))

        if data_vencimento:
            try:
                normalizar_data(data_vencimento)
            except ValueError:
                flash('Informe uma data valida.', 'danger')
                return redirect(url_for('veiculos.form_lembrete', id=id) if id else url_for('veiculos.form_lembrete'))

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT VeiculoId
                FROM APP_Veiculos
                WHERE VeiculoId = ? AND UsuarioId = ?
            """, (veiculo_id, usuario_id))
            if not cursor.fetchone():
                flash('Veiculo nao encontrado.', 'warning')
                return redirect(url_for('veiculos.form_lembrete', id=id) if id else url_for('veiculos.form_lembrete'))

            if id:
                cursor.execute("""
                    UPDATE APP_VeiculoLembretes
                    SET VeiculoId = ?, Tipo = ?, Titulo = ?, DataVencimento = ?,
                        KmVencimento = ?, RecorrenciaMeses = ?, IntervaloKm = ?,
                        ValorEstimado = ?, Concluido = ?, Observacoes = ?,
                        DataAtualizacao = SYSUTCDATETIME()
                    WHERE LembreteId = ? AND UsuarioId = ?
                """, (
                    veiculo_id, tipo, titulo, data_vencimento, km_vencimento,
                    recorrencia_meses, intervalo_km, valor_estimado, concluido,
                    observacoes, id, usuario_id,
                ))
                flash('Lembrete atualizado com sucesso.', 'success')
            else:
                cursor.execute("""
                    INSERT INTO APP_VeiculoLembretes
                    (VeiculoId, UsuarioId, Tipo, Titulo, DataVencimento, KmVencimento,
                     RecorrenciaMeses, IntervaloKm, ValorEstimado, Concluido, Observacoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    veiculo_id, usuario_id, tipo, titulo, data_vencimento,
                    km_vencimento, recorrencia_meses, intervalo_km, valor_estimado,
                    concluido, observacoes,
                ))
                flash('Lembrete cadastrado com sucesso.', 'success')

        return redirect(url_for('veiculos.lista'))

    lembrete = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT LembreteId, VeiculoId, Tipo, Titulo, DataVencimento, KmVencimento,
                       RecorrenciaMeses, IntervaloKm, ValorEstimado, Concluido, Observacoes
                FROM APP_VeiculoLembretes
                WHERE LembreteId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            lembrete = cursor.fetchone()

    veiculo_id_pre = request.args.get('veiculo_id')
    return render_template(
        'veiculos/form_lembrete.html',
        lembrete=lembrete,
        veiculos=veiculos,
        tipos_lembrete=TIPOS_LEMBRETE,
        veiculo_id_pre=veiculo_id_pre,
    )


@veiculos_bp.route('/quilometragem/<int:id>', methods=['POST'])
def atualizar_quilometragem(id):
    usuario_id = usuario_atual_id()
    quilometragem = parse_int(request.form.get('quilometragem_atual'))

    if quilometragem is None or quilometragem < 0:
        flash('Informe uma quilometragem valida.', 'danger')
        return redirect(url_for('veiculos.lista'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE APP_Veiculos
            SET QuilometragemAtual = ?, DataAtualizacao = SYSUTCDATETIME()
            WHERE VeiculoId = ? AND UsuarioId = ?
        """, (quilometragem, id, usuario_id))

    flash('Quilometragem atualizada.', 'success')
    return redirect(url_for('veiculos.lista'))


@veiculos_bp.route('/lembrete/concluir/<int:id>', methods=['POST'])
def concluir_lembrete(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT L.LembreteId, L.VeiculoId, L.DataVencimento, L.KmVencimento,
                   L.RecorrenciaMeses, L.IntervaloKm, V.QuilometragemAtual
            FROM APP_VeiculoLembretes L
            JOIN APP_Veiculos V ON L.VeiculoId = V.VeiculoId AND V.UsuarioId = L.UsuarioId
            WHERE L.LembreteId = ? AND L.UsuarioId = ?
        """, (id, usuario_id))
        lembrete = cursor.fetchone()

        if not lembrete:
            flash('Lembrete nao encontrado.', 'warning')
            return redirect(url_for('veiculos.lista'))

        data_vencimento = normalizar_data(lembrete.DataVencimento)
        recorrencia_meses = lembrete.RecorrenciaMeses
        intervalo_km = lembrete.IntervaloKm
        km_vencimento = lembrete.KmVencimento

        nova_data = None
        novo_km = None
        concluido = 1

        if data_vencimento and recorrencia_meses:
            nova_data = somar_meses(data_vencimento, int(recorrencia_meses))
            hoje = date.today()
            while nova_data <= hoje:
                nova_data = somar_meses(nova_data, int(recorrencia_meses))
            concluido = 0

        if km_vencimento is not None and intervalo_km:
            base_km = max(int(km_vencimento), int(lembrete.QuilometragemAtual or 0))
            novo_km = base_km + int(intervalo_km)
            concluido = 0

        cursor.execute("""
            UPDATE APP_VeiculoLembretes
            SET DataVencimento = COALESCE(?, DataVencimento),
                KmVencimento = COALESCE(?, KmVencimento),
                Concluido = ?,
                UltimaConclusao = SYSUTCDATETIME(),
                DataAtualizacao = SYSUTCDATETIME()
            WHERE LembreteId = ? AND UsuarioId = ?
        """, (nova_data, novo_km, concluido, id, usuario_id))

    flash('Lembrete concluido.', 'success')
    return redirect(url_for('veiculos.lista'))


@veiculos_bp.route('/lembrete/excluir/<int:id>', methods=['POST'])
def excluir_lembrete(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM APP_VeiculoLembretes WHERE LembreteId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Lembrete removido.', 'warning')
    return redirect(url_for('veiculos.lista'))


@veiculos_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM APP_VeiculoLembretes WHERE VeiculoId = ? AND UsuarioId = ?", (id, usuario_id))
        cursor.execute("DELETE FROM APP_Veiculos WHERE VeiculoId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Veiculo removido.', 'warning')
    return redirect(url_for('veiculos.lista'))

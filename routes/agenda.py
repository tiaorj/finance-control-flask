from datetime import date, datetime

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from database import get_db_cursor


agenda_bp = Blueprint('agenda', __name__, url_prefix='/app/agenda')


def usuario_atual_id():
    return int(current_user.get_id())


def normalizar_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor:
        return datetime.strptime(valor[:10], '%Y-%m-%d').date()
    return None


def ler_data_query(nome):
    valor = request.args.get(nome)
    try:
        return datetime.strptime(valor[:10], '%Y-%m-%d').date() if valor else None
    except (TypeError, ValueError):
        return None


def filtro_periodo(campo, params, inicio, fim):
    filtros = []
    if inicio:
        filtros.append(f"{campo} >= ?")
        params.append(inicio)
    if fim:
        filtros.append(f"{campo} < ?")
        params.append(fim)
    return filtros


def data_iso(valor):
    data = normalizar_data(valor)
    return data.isoformat() if data else None


@agenda_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))


@agenda_bp.route('/')
@agenda_bp.route('', strict_slashes=False)
def calendario():
    return render_template('agenda/calendario.html')


@agenda_bp.route('/eventos')
def eventos():
    usuario_id = usuario_atual_id()
    inicio = ler_data_query('start')
    fim = ler_data_query('end')
    eventos_calendario = []

    with get_db_cursor() as cursor:
        params = [usuario_id]
        filtros = [
            "UsuarioId = ?",
            "Pago = 0",
            "DataVencimento IS NOT NULL",
        ]
        filtros.extend(filtro_periodo("DataVencimento", params, inicio, fim))
        cursor.execute(f"""
            SELECT LancamentoId, Descricao, DataVencimento
            FROM FIN_Lancamentos
            WHERE {' AND '.join(filtros)}
            ORDER BY DataVencimento ASC, Descricao ASC
        """, tuple(params))
        for item in cursor.fetchall():
            data_evento = normalizar_data(item.DataVencimento)
            if not data_evento:
                continue
            eventos_calendario.append({
                'id': f'fin-{item.LancamentoId}',
                'title': f'💰 {item.Descricao or "Lançamento pendente"}',
                'start': data_evento.isoformat(),
                'url': url_for('financas.dashboard', mes=data_evento.month, ano=data_evento.year),
                'extendedProps': {'tipo': 'financeiro'},
            })

        params = [usuario_id]
        filtros = [
            "UsuarioId = ?",
            "Ativa = 1",
            "ProximaData IS NOT NULL",
        ]
        filtros.extend(filtro_periodo("ProximaData", params, inicio, fim))
        cursor.execute(f"""
            SELECT TarefaId, Titulo, ProximaData
            FROM APP_TarefasRecorrentes
            WHERE {' AND '.join(filtros)}
            ORDER BY ProximaData ASC, Titulo ASC
        """, tuple(params))
        for item in cursor.fetchall():
            inicio_evento = data_iso(item.ProximaData)
            if not inicio_evento:
                continue
            eventos_calendario.append({
                'id': f'tarefa-{item.TarefaId}',
                'title': f'✅ {item.Titulo or "Tarefa recorrente"}',
                'start': inicio_evento,
                'url': url_for('tarefas.form', id=item.TarefaId),
                'extendedProps': {'tipo': 'tarefa'},
            })

        params = [usuario_id]
        filtros = [
            "L.UsuarioId = ?",
            "L.Concluido = 0",
            "L.DataVencimento IS NOT NULL",
        ]
        filtros.extend(filtro_periodo("L.DataVencimento", params, inicio, fim))
        cursor.execute(f"""
            SELECT L.LembreteId, L.Titulo, L.DataVencimento, V.Apelido
            FROM APP_VeiculoLembretes L
            LEFT JOIN APP_Veiculos V
                ON V.VeiculoId = L.VeiculoId
                AND V.UsuarioId = L.UsuarioId
            WHERE {' AND '.join(filtros)}
            ORDER BY L.DataVencimento ASC, L.Titulo ASC
        """, tuple(params))
        for item in cursor.fetchall():
            inicio_evento = data_iso(item.DataVencimento)
            if not inicio_evento:
                continue
            titulo = item.Titulo or 'Lembrete de veículo'
            if item.Apelido:
                titulo = f'{item.Apelido}: {titulo}'
            eventos_calendario.append({
                'id': f'veiculo-{item.LembreteId}',
                'title': f'🚗 {titulo}',
                'start': inicio_evento,
                'url': url_for('veiculos.form_lembrete', id=item.LembreteId),
                'extendedProps': {'tipo': 'veiculo'},
            })

    return jsonify(eventos_calendario)

from calendar import monthrange
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from database import get_db_cursor


tarefas_bp = Blueprint('tarefas', __name__, url_prefix='/app/tarefas')

PERIODICIDADES = {
    'mensal': {'label': 'Mensal', 'meses': 1},
    'bimestral': {'label': 'Bimestral', 'meses': 2},
    'trimestral': {'label': 'Trimestral', 'meses': 3},
    'semestral': {'label': 'Semestral', 'meses': 6},
    'anual': {'label': 'Anual', 'meses': 12},
    'personalizado': {'label': 'Personalizado', 'meses': None},
}

CATEGORIAS = [
    'Casa',
    'Documentos',
    'Financeiro',
    'Pets',
    'Saude',
    'Veiculo',
    'Outros',
]


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


def somar_meses(data_base, meses):
    mes = data_base.month - 1 + meses
    ano = data_base.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data_base.day, monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def intervalo_da_periodicidade(periodicidade, intervalo_personalizado):
    if periodicidade != 'personalizado':
        return PERIODICIDADES[periodicidade]['meses']

    try:
        return max(int(intervalo_personalizado or 1), 1)
    except ValueError:
        return 1


def rotulo_periodicidade(periodicidade, intervalo_meses):
    if periodicidade == 'personalizado':
        return f'A cada {intervalo_meses} meses'
    return PERIODICIDADES.get(periodicidade, PERIODICIDADES['mensal'])['label']


def montar_tarefa(row, hoje=None):
    hoje = hoje or date.today()
    proxima_data = normalizar_data(row.ProximaData)
    dias = (proxima_data - hoje).days if proxima_data else None

    if dias is None:
        status = 'sem_data'
        status_texto = 'Sem data'
    elif dias < 0:
        status = 'atrasada'
        status_texto = f'{abs(dias)} dias atrasada'
    elif dias == 0:
        status = 'hoje'
        status_texto = 'Vence hoje'
    elif dias <= 7:
        status = 'semana'
        status_texto = f'Em {dias} dias'
    else:
        status = 'futura'
        status_texto = f'Em {dias} dias'

    intervalo_meses = int(row.IntervaloMeses or 1)
    periodicidade = (row.Periodicidade or 'mensal').lower()

    return {
        'id': row.TarefaId,
        'titulo': row.Titulo,
        'categoria': row.Categoria or 'Outros',
        'periodicidade': periodicidade,
        'intervalo_meses': intervalo_meses,
        'periodicidade_label': rotulo_periodicidade(periodicidade, intervalo_meses),
        'proxima_data': proxima_data,
        'ultima_conclusao': row.UltimaConclusao,
        'ativa': bool(row.Ativa),
        'observacoes': row.Observacoes,
        'dias': dias,
        'status': status,
        'status_texto': status_texto,
    }


def montar_resumo_tarefas(cursor, usuario_id, hoje=None):
    hoje = hoje or date.today()
    fim_mes = date(hoje.year, hoje.month, monthrange(hoje.year, hoje.month)[1])

    cursor.execute("""
        SELECT TarefaId, Titulo, Categoria, Periodicidade, IntervaloMeses,
               ProximaData, UltimaConclusao, Ativa, Observacoes
        FROM APP_TarefasRecorrentes
        WHERE UsuarioId = ? AND Ativa = 1
        ORDER BY ProximaData ASC, Titulo ASC
    """, (usuario_id,))
    tarefas = [montar_tarefa(row, hoje) for row in cursor.fetchall()]

    tarefas_do_mes = [
        tarefa for tarefa in tarefas
        if tarefa['proxima_data'] and tarefa['proxima_data'] <= fim_mes
    ]

    return {
        'tarefas': tarefas,
        'proximas': tarefas_do_mes[:5],
        'ativas': len(tarefas),
        'do_mes': len(tarefas_do_mes),
        'atrasadas': len([tarefa for tarefa in tarefas if tarefa['dias'] is not None and tarefa['dias'] < 0]),
        'hoje': len([tarefa for tarefa in tarefas if tarefa['dias'] == 0]),
        'semana': len([tarefa for tarefa in tarefas if tarefa['dias'] is not None and 0 <= tarefa['dias'] <= 7]),
    }


@tarefas_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))


@tarefas_bp.route('/')
def lista():
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        resumo = montar_resumo_tarefas(cursor, usuario_id)
        cursor.execute("""
            SELECT TOP 8 T.Titulo, TC.DataConclusao, TC.ProximaDataGerada, TC.Observacao
            FROM APP_TarefaConclusoes TC
            JOIN APP_TarefasRecorrentes T ON TC.TarefaId = T.TarefaId
            WHERE TC.UsuarioId = ?
            ORDER BY TC.DataConclusao DESC
        """, (usuario_id,))
        conclusoes = cursor.fetchall()

    return render_template(
        'tarefas/lista.html',
        tarefas=resumo['tarefas'],
        resumo=resumo,
        conclusoes=conclusoes,
    )


@tarefas_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@tarefas_bp.route('/form/<int:id>', methods=['GET', 'POST'])
def form(id):
    usuario_id = usuario_atual_id()

    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        categoria = (request.form.get('categoria') or '').strip() or None
        periodicidade = (request.form.get('periodicidade') or 'mensal').lower()
        proxima_data = request.form.get('proxima_data')
        observacoes = (request.form.get('observacoes') or '').strip() or None
        ativa = 1 if request.form.get('ativa') == 'on' else 0

        if not titulo:
            flash('Informe o titulo da tarefa.', 'danger')
            return redirect(url_for('tarefas.form', id=id) if id else url_for('tarefas.form'))

        if periodicidade not in PERIODICIDADES:
            flash('Selecione uma periodicidade valida.', 'danger')
            return redirect(url_for('tarefas.form', id=id) if id else url_for('tarefas.form'))

        intervalo_meses = intervalo_da_periodicidade(periodicidade, request.form.get('intervalo_meses'))

        try:
            proxima_data_normalizada = normalizar_data(proxima_data)
        except (TypeError, ValueError):
            flash('Informe a proxima data.', 'danger')
            return redirect(url_for('tarefas.form', id=id) if id else url_for('tarefas.form'))

        if not proxima_data_normalizada:
            flash('Informe a proxima data.', 'danger')
            return redirect(url_for('tarefas.form', id=id) if id else url_for('tarefas.form'))

        with get_db_cursor() as cursor:
            if id:
                cursor.execute("""
                    UPDATE APP_TarefasRecorrentes
                    SET Titulo = ?, Categoria = ?, Periodicidade = ?, IntervaloMeses = ?,
                        ProximaData = ?, Ativa = ?, Observacoes = ?,
                        DataAtualizacao = SYSUTCDATETIME()
                    WHERE TarefaId = ? AND UsuarioId = ?
                """, (titulo, categoria, periodicidade, intervalo_meses, proxima_data, ativa, observacoes, id, usuario_id))
                flash('Tarefa atualizada com sucesso.', 'success')
            else:
                cursor.execute("""
                    INSERT INTO APP_TarefasRecorrentes
                    (UsuarioId, Titulo, Categoria, Periodicidade, IntervaloMeses, ProximaData, Ativa, Observacoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, titulo, categoria, periodicidade, intervalo_meses, proxima_data, ativa, observacoes))
                flash('Tarefa criada com sucesso.', 'success')

        return redirect(url_for('tarefas.lista'))

    tarefa = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT TarefaId, Titulo, Categoria, Periodicidade, IntervaloMeses,
                       ProximaData, UltimaConclusao, Ativa, Observacoes
                FROM APP_TarefasRecorrentes
                WHERE TarefaId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            tarefa = cursor.fetchone()

    return render_template(
        'tarefas/form.html',
        tarefa=tarefa,
        periodicidades=PERIODICIDADES,
        categorias=CATEGORIAS,
    )


@tarefas_bp.route('/concluir/<int:id>', methods=['POST'])
def concluir(id):
    usuario_id = usuario_atual_id()
    observacao = (request.form.get('observacao') or '').strip() or None
    next_url = request.form.get('next')
    destino = next_url if next_url and next_url.startswith('/') and not next_url.startswith('//') else url_for('tarefas.lista')

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT TarefaId, ProximaData, IntervaloMeses
            FROM APP_TarefasRecorrentes
            WHERE TarefaId = ? AND UsuarioId = ? AND Ativa = 1
        """, (id, usuario_id))
        tarefa = cursor.fetchone()

        if not tarefa:
            flash('Tarefa nao encontrada.', 'warning')
            return redirect(destino)

        proxima_data = normalizar_data(tarefa.ProximaData) or date.today()
        intervalo_meses = int(tarefa.IntervaloMeses or 1)
        nova_data = somar_meses(proxima_data, intervalo_meses)
        hoje = date.today()

        while nova_data <= hoje:
            nova_data = somar_meses(nova_data, intervalo_meses)

        cursor.execute("""
            INSERT INTO APP_TarefaConclusoes (TarefaId, UsuarioId, ProximaDataGerada, Observacao)
            VALUES (?, ?, ?, ?)
        """, (id, usuario_id, nova_data, observacao))

        cursor.execute("""
            UPDATE APP_TarefasRecorrentes
            SET ProximaData = ?, UltimaConclusao = SYSUTCDATETIME(),
                DataAtualizacao = SYSUTCDATETIME()
            WHERE TarefaId = ? AND UsuarioId = ?
        """, (nova_data, id, usuario_id))

    flash('Tarefa concluida e reagendada.', 'success')
    return redirect(destino)


@tarefas_bp.route('/pular/<int:id>', methods=['POST'])
def pular(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT TarefaId, ProximaData, IntervaloMeses
            FROM APP_TarefasRecorrentes
            WHERE TarefaId = ? AND UsuarioId = ? AND Ativa = 1
        """, (id, usuario_id))
        tarefa = cursor.fetchone()

        if not tarefa:
            flash('Tarefa nao encontrada.', 'warning')
            return redirect(url_for('tarefas.lista'))

        proxima_data = normalizar_data(tarefa.ProximaData) or date.today()
        intervalo_meses = int(tarefa.IntervaloMeses or 1)
        nova_data = somar_meses(proxima_data, intervalo_meses)
        hoje = date.today()

        while nova_data <= hoje:
            nova_data = somar_meses(nova_data, intervalo_meses)

        cursor.execute("""
            UPDATE APP_TarefasRecorrentes
            SET ProximaData = ?, DataAtualizacao = SYSUTCDATETIME()
            WHERE TarefaId = ? AND UsuarioId = ?
        """, (nova_data, id, usuario_id))

    flash('Tarefa reagendada.', 'success')
    return redirect(url_for('tarefas.lista'))


@tarefas_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM APP_TarefaConclusoes WHERE TarefaId = ? AND UsuarioId = ?", (id, usuario_id))
        cursor.execute("DELETE FROM APP_TarefasRecorrentes WHERE TarefaId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Tarefa removida.', 'warning')
    return redirect(url_for('tarefas.lista'))

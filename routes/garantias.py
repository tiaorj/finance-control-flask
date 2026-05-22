from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from database import get_db_cursor


garantias_bp = Blueprint('garantias', __name__, url_prefix='/app/garantias')

CATEGORIAS = [
    'Eletrodomestico',
    'Eletronico',
    'Informatica',
    'Moveis',
    'Ferramentas',
    'Casa',
    'Outro',
]

EXTENSOES_NOTA_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png', '.webp'}


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


def salvar_arquivo_nota(usuario_id):
    arquivo = request.files.get('nota_arquivo')
    if not arquivo or not arquivo.filename:
        return None

    nome_original = secure_filename(arquivo.filename)
    extensao = Path(nome_original).suffix.lower()
    if extensao not in EXTENSOES_NOTA_PERMITIDAS:
        raise ValueError('Envie a nota em PDF, JPG, PNG ou WEBP.')

    pasta_destino = Path(current_app.static_folder) / 'uploads' / 'garantias'
    pasta_destino.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%Y%m%d%H%M%S%f')
    nome_arquivo = f'nota_{usuario_id}_{timestamp}{extensao}'
    arquivo.save(pasta_destino / nome_arquivo)
    return f'uploads/garantias/{nome_arquivo}'


def status_garantia(row, hoje=None):
    hoje = hoje or datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    data_compra = normalizar_data(row.DataCompra)
    meses = int(row.MesesGarantia or 0)
    data_fim = somar_meses(data_compra, meses) if data_compra else None
    dias = (data_fim - hoje).days if data_fim else None

    if dias is None:
        return 'sem_data', 'Sem data', data_fim, dias
    if dias < 0:
        return 'vencida', 'Garantia vencida', data_fim, dias
    if dias == 0:
        return 'vence_hoje', 'Vence hoje', data_fim, dias
    if dias <= 30:
        return 'vence_breve', f'Vence em {dias} dias', data_fim, dias
    return 'vigente', 'Em garantia', data_fim, dias


def montar_bem(row, hoje=None):
    status, status_texto, data_fim, dias = status_garantia(row, hoje)

    return {
        'id': row.BemId,
        'nome': row.Nome,
        'categoria': row.Categoria or 'Outro',
        'marca': row.Marca,
        'modelo': row.Modelo,
        'data_compra': normalizar_data(row.DataCompra),
        'meses_garantia': int(row.MesesGarantia or 0),
        'data_fim': data_fim,
        'dias': dias,
        'valor_compra': float(row.ValorCompra or 0),
        'local_compra': row.LocalCompra,
        'nota_url': row.NotaFiscalUrl,
        'nota_arquivo': row.NotaFiscalArquivo,
        'ativo': bool(row.Ativo),
        'observacoes': row.Observacoes,
        'status': status,
        'status_texto': status_texto,
        'tem_nota': bool(row.NotaFiscalUrl or row.NotaFiscalArquivo),
    }


def montar_resumo_garantias(cursor, usuario_id, hoje=None):
    hoje = hoje or datetime.now(ZoneInfo('America/Sao_Paulo')).date()

    cursor.execute("""
        SELECT BemId, Nome, Categoria, Marca, Modelo, DataCompra, MesesGarantia,
               ValorCompra, LocalCompra, NotaFiscalUrl, NotaFiscalArquivo,
               Ativo, Observacoes
        FROM APP_BensGarantia
        WHERE UsuarioId = ? AND Ativo = 1
        ORDER BY DataCompra DESC, Nome ASC
    """, (usuario_id,))
    bens = [montar_bem(row, hoje) for row in cursor.fetchall()]

    valor_total = sum(item['valor_compra'] for item in bens)
    vigentes = [item for item in bens if item['status'] in ('vigente', 'vence_breve', 'vence_hoje')]
    vencidas = [item for item in bens if item['status'] == 'vencida']
    vencem_breve = [item for item in bens if item['status'] in ('vence_breve', 'vence_hoje')]

    proximas = sorted(
        [item for item in bens if item['data_fim']],
        key=lambda item: (item['data_fim'], item['nome'])
    )

    return {
        'bens': bens,
        'total': len(bens),
        'vigentes': len(vigentes),
        'vencidas': len(vencidas),
        'vencem_breve': len(vencem_breve),
        'com_nota': len([item for item in bens if item['tem_nota']]),
        'valor_total': valor_total,
        'proximas': proximas[:5],
    }


@garantias_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))


@garantias_bp.route('/')
def lista():
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        resumo = montar_resumo_garantias(cursor, usuario_id)

    return render_template(
        'garantias/lista.html',
        bens=resumo['bens'],
        resumo=resumo,
    )


@garantias_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@garantias_bp.route('/form/<int:id>', methods=['GET', 'POST'])
def form(id):
    usuario_id = usuario_atual_id()

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        categoria = (request.form.get('categoria') or '').strip() or None
        marca = (request.form.get('marca') or '').strip() or None
        modelo = (request.form.get('modelo') or '').strip() or None
        data_compra = request.form.get('data_compra')
        meses_garantia = parse_int(request.form.get('meses_garantia'), 0)
        valor_compra = parse_money(request.form.get('valor_compra'))
        local_compra = (request.form.get('local_compra') or '').strip() or None
        nota_url = (request.form.get('nota_url') or '').strip() or None
        nota_arquivo = (request.form.get('nota_arquivo_atual') or '').strip() or None
        observacoes = (request.form.get('observacoes') or '').strip() or None
        ativo = 1 if request.form.get('ativo') == 'on' else 0

        if not nome:
            flash('Informe o nome do bem.', 'danger')
            return redirect(url_for('garantias.form', id=id) if id else url_for('garantias.form'))

        if categoria and categoria not in CATEGORIAS:
            flash('Selecione uma categoria valida.', 'danger')
            return redirect(url_for('garantias.form', id=id) if id else url_for('garantias.form'))

        if meses_garantia is None or meses_garantia < 0:
            flash('Informe o tempo de garantia em meses.', 'danger')
            return redirect(url_for('garantias.form', id=id) if id else url_for('garantias.form'))

        try:
            data_compra_normalizada = normalizar_data(data_compra)
        except (TypeError, ValueError):
            flash('Informe uma data de compra valida.', 'danger')
            return redirect(url_for('garantias.form', id=id) if id else url_for('garantias.form'))

        if not data_compra_normalizada:
            flash('Informe a data de compra.', 'danger')
            return redirect(url_for('garantias.form', id=id) if id else url_for('garantias.form'))

        try:
            arquivo_enviado = salvar_arquivo_nota(usuario_id)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('garantias.form', id=id) if id else url_for('garantias.form'))

        if arquivo_enviado:
            nota_arquivo = arquivo_enviado

        with get_db_cursor() as cursor:
            if id:
                cursor.execute("""
                    UPDATE APP_BensGarantia
                    SET Nome = ?, Categoria = ?, Marca = ?, Modelo = ?, DataCompra = ?,
                        MesesGarantia = ?, ValorCompra = ?, LocalCompra = ?,
                        NotaFiscalUrl = ?, NotaFiscalArquivo = ?, Ativo = ?,
                        Observacoes = ?, DataAtualizacao = SYSUTCDATETIME()
                    WHERE BemId = ? AND UsuarioId = ?
                """, (
                    nome, categoria, marca, modelo, data_compra, meses_garantia,
                    valor_compra, local_compra, nota_url, nota_arquivo, ativo,
                    observacoes, id, usuario_id,
                ))
                flash('Bem atualizado com sucesso.', 'success')
            else:
                cursor.execute("""
                    INSERT INTO APP_BensGarantia
                    (UsuarioId, Nome, Categoria, Marca, Modelo, DataCompra,
                     MesesGarantia, ValorCompra, LocalCompra, NotaFiscalUrl,
                     NotaFiscalArquivo, Ativo, Observacoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    usuario_id, nome, categoria, marca, modelo, data_compra,
                    meses_garantia, valor_compra, local_compra, nota_url,
                    nota_arquivo, ativo, observacoes,
                ))
                flash('Bem cadastrado com sucesso.', 'success')

        return redirect(url_for('garantias.lista'))

    bem = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT BemId, Nome, Categoria, Marca, Modelo, DataCompra, MesesGarantia,
                       ValorCompra, LocalCompra, NotaFiscalUrl, NotaFiscalArquivo,
                       Ativo, Observacoes
                FROM APP_BensGarantia
                WHERE BemId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            bem = cursor.fetchone()

    return render_template('garantias/form.html', bem=bem, categorias=CATEGORIAS)


@garantias_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM APP_BensGarantia WHERE BemId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Bem removido.', 'warning')
    return redirect(url_for('garantias.lista'))

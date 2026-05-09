from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from database import get_db_cursor


assinaturas_bp = Blueprint('assinaturas', __name__, url_prefix='/app/assinaturas')
CICLOS_VALIDOS = {'mensal', 'anual'}


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


def garantir_tabela_assinaturas(cursor):
    cursor.execute("""
        IF OBJECT_ID('dbo.FIN_Assinaturas', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.FIN_Assinaturas (
                AssinaturaId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                UsuarioId INT NOT NULL,
                Nome NVARCHAR(120) NOT NULL,
                Categoria NVARCHAR(80) NULL,
                Valor DECIMAL(12,2) NOT NULL,
                Ciclo NVARCHAR(20) NOT NULL,
                DataRenovacao DATE NOT NULL,
                Ativa BIT NOT NULL DEFAULT 1,
                Observacoes NVARCHAR(500) NULL,
                DataCriacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                CONSTRAINT FK_FIN_Assinaturas_Usuarios
                    FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId),
                CONSTRAINT CK_FIN_Assinaturas_Ciclo
                    CHECK (Ciclo IN ('mensal', 'anual'))
            )
        END
    """)


def normalizar_data(valor):
    if isinstance(valor, date):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        return datetime.strptime(valor[:10], '%Y-%m-%d').date()
    return None


def valor_mensalizado(valor, ciclo):
    valor = float(valor or 0)
    return valor / 12 if ciclo == 'anual' else valor


def montar_resumo_assinaturas(cursor, usuario_id, hoje=None):
    garantir_tabela_assinaturas(cursor)
    hoje = hoje or date.today()

    cursor.execute("""
        SELECT AssinaturaId, Nome, Categoria, Valor, Ciclo, DataRenovacao, Ativa
        FROM FIN_Assinaturas
        WHERE UsuarioId = ? AND Ativa = 1
        ORDER BY DataRenovacao ASC, Nome ASC
    """, (usuario_id,))
    assinaturas = cursor.fetchall()

    total_mensal = 0.0
    proximas = []
    for assinatura in assinaturas:
        ciclo = (assinatura.Ciclo or 'mensal').lower()
        data_renovacao = normalizar_data(assinatura.DataRenovacao)
        total_mensal += valor_mensalizado(assinatura.Valor, ciclo)

        dias = (data_renovacao - hoje).days if data_renovacao else None
        if dias is not None and 0 <= dias <= 7:
            proximas.append({
                'id': assinatura.AssinaturaId,
                'nome': assinatura.Nome,
                'valor': float(assinatura.Valor or 0),
                'ciclo': ciclo,
                'data_renovacao': data_renovacao,
                'dias': dias,
            })

    return {
        'total_mensal': total_mensal,
        'total_anual': total_mensal * 12,
        'ativas': len(assinaturas),
        'proximas': proximas[:5],
    }


@assinaturas_bp.before_request
def exigir_login():
    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('admin.login', next=next_url))


@assinaturas_bp.route('/')
def lista():
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        garantir_tabela_assinaturas(cursor)
        resumo = montar_resumo_assinaturas(cursor, usuario_id)
        cursor.execute("""
            SELECT AssinaturaId, Nome, Categoria, Valor, Ciclo, DataRenovacao, Ativa, Observacoes
            FROM FIN_Assinaturas
            WHERE UsuarioId = ?
            ORDER BY Ativa DESC, DataRenovacao ASC, Nome ASC
        """, (usuario_id,))
        assinaturas_rows = cursor.fetchall()

    hoje = date.today()
    assinaturas = []
    for item in assinaturas_rows:
        data_renovacao = normalizar_data(item.DataRenovacao)
        dias = (data_renovacao - hoje).days if data_renovacao else None
        assinaturas.append({
            'id': item.AssinaturaId,
            'nome': item.Nome,
            'categoria': item.Categoria,
            'valor': float(item.Valor or 0),
            'valor_mensal': valor_mensalizado(item.Valor, item.Ciclo),
            'ciclo': item.Ciclo,
            'data_renovacao': data_renovacao,
            'ativa': bool(item.Ativa),
            'observacoes': item.Observacoes,
            'dias': dias,
        })

    return render_template(
        'assinaturas/lista.html',
        assinaturas=assinaturas,
        resumo=resumo,
    )


@assinaturas_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@assinaturas_bp.route('/form/<int:id>', methods=['GET', 'POST'])
def form(id):
    usuario_id = usuario_atual_id()

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        categoria = (request.form.get('categoria') or '').strip() or None
        valor = parse_money(request.form.get('valor'))
        ciclo = (request.form.get('ciclo') or 'mensal').lower()
        data_renovacao = request.form.get('data_renovacao')
        observacoes = (request.form.get('observacoes') or '').strip() or None
        ativa = 1 if request.form.get('ativa') == 'on' else 0

        if not nome:
            flash('Informe o nome da assinatura.', 'danger')
            return redirect(url_for('assinaturas.form', id=id) if id else url_for('assinaturas.form'))

        if valor <= 0:
            flash('Informe um valor maior que zero.', 'danger')
            return redirect(url_for('assinaturas.form', id=id) if id else url_for('assinaturas.form'))

        if ciclo not in CICLOS_VALIDOS:
            flash('Selecione um ciclo válido.', 'danger')
            return redirect(url_for('assinaturas.form', id=id) if id else url_for('assinaturas.form'))

        try:
            normalizar_data(data_renovacao)
        except (TypeError, ValueError):
            flash('Informe a próxima renovação.', 'danger')
            return redirect(url_for('assinaturas.form', id=id) if id else url_for('assinaturas.form'))

        with get_db_cursor() as cursor:
            garantir_tabela_assinaturas(cursor)
            if id:
                cursor.execute("""
                    UPDATE FIN_Assinaturas
                    SET Nome = ?, Categoria = ?, Valor = ?, Ciclo = ?, DataRenovacao = ?,
                        Ativa = ?, Observacoes = ?, DataAtualizacao = SYSUTCDATETIME()
                    WHERE AssinaturaId = ? AND UsuarioId = ?
                """, (nome, categoria, valor, ciclo, data_renovacao, ativa, observacoes, id, usuario_id))
                flash('Assinatura atualizada com sucesso!', 'success')
            else:
                cursor.execute("""
                    INSERT INTO FIN_Assinaturas
                    (UsuarioId, Nome, Categoria, Valor, Ciclo, DataRenovacao, Ativa, Observacoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, nome, categoria, valor, ciclo, data_renovacao, ativa, observacoes))
                flash('Assinatura cadastrada com sucesso!', 'success')

        return redirect(url_for('assinaturas.lista'))

    assinatura = None
    if id:
        with get_db_cursor() as cursor:
            garantir_tabela_assinaturas(cursor)
            cursor.execute("""
                SELECT AssinaturaId, Nome, Categoria, Valor, Ciclo, DataRenovacao, Ativa, Observacoes
                FROM FIN_Assinaturas
                WHERE AssinaturaId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            assinatura = cursor.fetchone()

    return render_template('assinaturas/form.html', assinatura=assinatura)


@assinaturas_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    usuario_id = usuario_atual_id()

    with get_db_cursor() as cursor:
        garantir_tabela_assinaturas(cursor)
        cursor.execute("DELETE FROM FIN_Assinaturas WHERE AssinaturaId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Assinatura removida.', 'warning')
    return redirect(url_for('assinaturas.lista'))

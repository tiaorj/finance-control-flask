from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_cursor
from routes.admin import login_required

formacao_bp = Blueprint('formacao_admin', __name__, url_prefix='/admin/formacao')

@formacao_bp.route('/')
@login_required
def lista():
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM FormacaoAcademica ORDER BY AnoInicio DESC")
        formacoes = cursor.fetchall()

    return render_template('admin/formacao_lista.html', formacoes=formacoes)

@formacao_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@formacao_bp.route('/form/<int:id>', methods=['GET', 'POST'])
@login_required
def form(id):
    if request.method == 'POST':
        nivel = request.form.get('nivel_escolaridade')
        curso = request.form.get('nome_curso')
        instituicao = request.form.get('nome_instituicao')
        inicio = request.form.get('ano_inicio')
        conclusao = request.form.get('ano_conclusao') or None

        with get_db_cursor() as cursor:
            if id:
                cursor.execute("""
                    UPDATE FormacaoAcademica
                    SET NivelEscolaridade=?, NomeCurso=?, NomeInstituicao=?, AnoInicio=?, AnoConclusao=?
                    WHERE FormacaoAcademicaId=?
                """, (nivel, curso, instituicao, inicio, conclusao, id))
            else:
                cursor.execute("""
                    INSERT INTO FormacaoAcademica (NivelEscolaridade, NomeCurso, NomeInstituicao, AnoInicio, AnoConclusao)
                    VALUES (?, ?, ?, ?, ?)
                """, (nivel, curso, instituicao, inicio, conclusao))

        flash('Registro de formação atualizado!', 'success')
        return redirect(url_for('formacao_admin.lista'))

    formacao = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM FormacaoAcademica WHERE FormacaoAcademicaId = ?", (id,))
            formacao = cursor.fetchone()

    return render_template('admin/form_formacao.html', formacao=formacao)

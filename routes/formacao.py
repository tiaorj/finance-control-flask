from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from database import get_db_cursor
from routes.admin import login_required

formacao_bp = Blueprint('formacao_admin', __name__, url_prefix='/admin/formacao')

@formacao_bp.route('/')
@login_required
def lista():
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT *
            FROM FormacaoAcademica
            WHERE UsuarioId = ?
            ORDER BY AnoInicio DESC
        """, (usuario_id,))
        formacoes = cursor.fetchall()

    return render_template('admin/formacao_lista.html', formacoes=formacoes)

@formacao_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@formacao_bp.route('/form/<int:id>', methods=['GET', 'POST'])
@login_required
def form(id):
    usuario_id = int(current_user.get_id())
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
                    WHERE FormacaoAcademicaId=? AND UsuarioId=?
                """, (nivel, curso, instituicao, inicio, conclusao, id, usuario_id))
            else:
                cursor.execute("""
                    INSERT INTO FormacaoAcademica (UsuarioId, NivelEscolaridade, NomeCurso, NomeInstituicao, AnoInicio, AnoConclusao)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (usuario_id, nivel, curso, instituicao, inicio, conclusao))

        flash('Registro de formação atualizado!', 'success')
        return redirect(url_for('formacao_admin.lista'))

    formacao = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT *
                FROM FormacaoAcademica
                WHERE FormacaoAcademicaId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            formacao = cursor.fetchone()

    return render_template('admin/form_formacao.html', formacao=formacao)

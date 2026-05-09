from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from database import get_db_cursor
from routes.admin import login_required

certificacoes_bp = Blueprint('certificacoes_admin', __name__, url_prefix='/admin/certificacoes')

@certificacoes_bp.route('/')
@login_required
def lista():
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT *
            FROM Certificacoes
            WHERE UsuarioId = ?
            ORDER BY Nome
        """, (usuario_id,))
        certificados = cursor.fetchall()

    return render_template('admin/certificacoes_lista.html', certificados=certificados)

@certificacoes_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@certificacoes_bp.route('/form/<int:id>', methods=['GET', 'POST'])
@login_required
def form(id):
    usuario_id = int(current_user.get_id())
    if request.method == 'POST':
        nome = request.form.get('nome')
        instituicao = request.form.get('instituicao')
        icone = request.form.get('icone')
        link = request.form.get('link')

        with get_db_cursor() as cursor:
            if id:
                cursor.execute("""
                    UPDATE Certificacoes SET Nome=?, Instituicao=?, IconeClass=?, LinkVerificacao=?
                    WHERE CertificacaoId=? AND UsuarioId=?
                """, (nome, instituicao, icone, link, id, usuario_id))
                flash('Certificação atualizada!', 'success')
            else:
                cursor.execute("""
                    INSERT INTO Certificacoes (UsuarioId, Nome, Instituicao, IconeClass, LinkVerificacao)
                    VALUES (?, ?, ?, ?, ?)
                """, (usuario_id, nome, instituicao, icone, link))
                flash('Certificação cadastrada com sucesso!', 'success')

        return redirect(url_for('certificacoes_admin.lista'))

    certificado = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT *
                FROM Certificacoes
                WHERE CertificacaoId = ? AND UsuarioId = ?
            """, (id, usuario_id))
            certificado = cursor.fetchone()

    return render_template('admin/form_certificacao.html', certificado=certificado)

@certificacoes_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM Certificacoes WHERE CertificacaoId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Certificação removida.', 'danger')
    return redirect(url_for('certificacoes_admin.lista'))

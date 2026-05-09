from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from database import get_db_cursor
from routes.admin import login_required

projetos_bp = Blueprint('projetos_admin', __name__, url_prefix='/admin/projetos')

# Rota Pública (Para o seu Portfólio)
@projetos_bp.route('/publico')
@login_required
def lista_publica():
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT *
            FROM Projeto
            WHERE UsuarioId = ?
            ORDER BY OrdemExibicao ASC
        """, (usuario_id,))
        projetos = cursor.fetchall()
    return render_template('projetos.html', projetos=projetos)

# Lista Administrativa
@projetos_bp.route('/')
@login_required
def lista():
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT *
            FROM Projeto
            WHERE UsuarioId = ?
            ORDER BY OrdemExibicao ASC
        """, (usuario_id,))
        projetos = cursor.fetchall()
    return render_template('admin/projetos_lista.html', projetos=projetos)
    

# ADICIONAR / EDITAR PROJETO
@projetos_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@projetos_bp.route('/form/<int:id>', methods=['GET', 'POST'])
@login_required
def form(id):    
    usuario_id = int(current_user.get_id())
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        tecnologias = request.form.get('tecnologias')
        descricao = request.form.get('descricao')
        icone = request.form.get('icone')
        ordem = request.form.get('ordem') or None
        link_github = request.form.get('link_github')
        link_live = request.form.get('link_live')

        with get_db_cursor() as cursor:
            if id:
                cursor.execute("""
                    UPDATE Projeto
                    SET Titulo=?, Tecnologias=?, Descricao=?, IconeClass=?,
                        OrdemExibicao=COALESCE(?, OrdemExibicao),
                        LinkGitHub=?, LinkLive=?
                    WHERE ProjetoId=? AND UsuarioId=?
                """, (titulo, tecnologias, descricao, icone, ordem, link_github, link_live, id, usuario_id))
            else:
                cursor.execute("""
                    INSERT INTO Projeto (UsuarioId, Titulo, Tecnologias, Descricao, IconeClass, OrdemExibicao, LinkGitHub, LinkLive)
                    VALUES (?, ?, ?, ?, ?, (SELECT ISNULL(MAX(OrdemExibicao), 0) + 1 FROM Projeto WHERE UsuarioId = ?), ?, ?)
                """, (usuario_id, titulo, tecnologias, descricao, icone, usuario_id, link_github, link_live))

            flash('Projeto cadastrado com sucesso!', 'success')
            return redirect(url_for('projetos_admin.lista'))

    projeto = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM Projeto WHERE ProjetoId = ? AND UsuarioId = ?", (id, usuario_id))
            projeto = cursor.fetchone()
    
    return render_template('admin/form_projeto.html', projeto=projeto)

# EXCLUIR PROJETO
@projetos_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM Projeto WHERE ProjetoId = ? AND UsuarioId = ?", (id, usuario_id))
        flash('Projeto removido.', 'danger')
    return redirect(url_for('projetos_admin.lista'))

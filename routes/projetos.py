from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_cursor
from routes.admin import login_required

projetos_bp = Blueprint('projetos_admin', __name__, url_prefix='/admin/projetos')

# Rota Pública (Para o seu Portfólio)
@projetos_bp.route('/publico')
def lista_publica():
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM Projeto ORDER BY OrdemExibicao ASC")
        projetos = cursor.fetchall()
    return render_template('projetos.html', projetos=projetos)

# Lista Administrativa
@projetos_bp.route('/')
@login_required
def lista():
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM Projeto ORDER BY OrdemExibicao ASC")
        projetos = cursor.fetchall()
    return render_template('admin/projetos_lista.html', projetos=projetos)
    

# ADICIONAR / EDITAR PROJETO
@projetos_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@projetos_bp.route('/form/<int:id>', methods=['GET', 'POST'])
@login_required
def form(id):    
    if request.method == 'POST':
        dados = (
            request.form.get('titulo'),
            request.form.get('tecnologias'),
            request.form.get('descricao'),
            request.form.get('icone'),
            request.form.get('ordem') or 0,
            request.form.get('link_github'),
            request.form.get('link_live')
        )

        with get_db_cursor() as cursor:
            if id:
                cursor.execute("""
                    UPDATE Projeto SET Titulo=?, Tecnologias=?, Descricao=?, IconeClass=?, OrdemExibicao=?, LinkGitHub=?, LinkLive=?
                    WHERE ProjetoId=?
                """, (*dados, id))
            else:
                cursor.execute("""
                    INSERT INTO Projeto (Titulo, Tecnologias, Descricao, IconeClass, OrdemExibicao, LinkGitHub, LinkLive)
                    VALUES (?, ?, ?, ?, (SELECT ISNULL(MAX(OrdemExibicao), 0) + 1 FROM Projeto), ?, ?)
                """, (dados))

            flash('Projeto cadastrado com sucesso!', 'success')
            return redirect(url_for('projetos_admin.lista'))

    projeto = None
    if id:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM Projeto WHERE ProjetoId = ?", (id,))
            projeto = cursor.fetchone()
    
    return render_template('admin/form_projeto.html', projeto=projeto)

# EXCLUIR PROJETO
@projetos_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM Projeto WHERE ProjetoId = ?", (id,))
        flash('Projeto removido.', 'danger')
    return redirect(url_for('projetos_admin.lista'))

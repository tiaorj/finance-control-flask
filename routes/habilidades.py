from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from database import get_db_cursor
from routes.admin import login_required

habilidades_bp = Blueprint('habilidades_admin', __name__, url_prefix='/admin/habilidades')

@habilidades_bp.route('/')
@login_required
def lista():
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT C.NomeCategoria, H.Descricao, H.HabilidadeId, C.HabilidadeCategoriaId
            FROM Habilidade H
            JOIN HabilidadeCategoria C ON H.HabilidadeCategoriaId = C.HabilidadeCategoriaId
            WHERE H.UsuarioId = ?
            ORDER BY C.NomeCategoria, H.Descricao
        """, (usuario_id,))
        habilidades = cursor.fetchall()

        cursor.execute("SELECT * FROM HabilidadeCategoria ORDER BY NomeCategoria")
        categorias = cursor.fetchall()

    return render_template('admin/habilidades_lista.html',
                           habilidades=habilidades,
                           categorias=categorias)

@habilidades_bp.route('/add', methods=['POST'])
@login_required
def adicionar():
    usuario_id = int(current_user.get_id())
    categoria_id = request.form.get('categoria_id')
    descricao = request.form.get('descricao')

    if not descricao:
        flash('A descrição da habilidade é obrigatória.', 'danger')
        return redirect(url_for('habilidades_admin.lista'))

    with get_db_cursor() as cursor:
        cursor.execute("INSERT INTO Habilidade (UsuarioId, HabilidadeCategoriaId, Descricao) VALUES (?, ?, ?)",
                       (usuario_id, categoria_id, descricao))

    flash('Habilidade adicionada!', 'success')
    return redirect(url_for('habilidades_admin.lista'))

@habilidades_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM Habilidade WHERE HabilidadeId = ? AND UsuarioId = ?", (id, usuario_id))

    flash('Habilidade removida.', 'warning')
    return redirect(url_for('habilidades_admin.lista'))

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db_cursor
from flask_login import UserMixin, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

class User(UserMixin):
    def __init__(self, usuario_id, nome, username=None):
        self.id = int(usuario_id)
        self.nome = nome
        self.username = username


def load_user(usuario_id):
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT UsuarioId, Nome, Username
            FROM Usuarios
            WHERE UsuarioId = ?
        """, (usuario_id,))
        usuario = cursor.fetchone()

    if not usuario:
        return None

    return User(usuario.UsuarioId, usuario.Nome, usuario.Username)


def safe_next_url(target):
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return None

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('usuario')
        senha_digitada = request.form.get('senha')

        with get_db_cursor() as cursor:
            cursor.execute("SELECT UsuarioId, Nome, SenhaHash FROM Usuarios WHERE Username = ?", (username,))
            usuario = cursor.fetchone()

            if usuario and check_password_hash(usuario.SenhaHash, senha_digitada):
                user = User(usuario.UsuarioId, usuario.Nome, username)
                login_user(user)

                session['admin_logado'] = True
                session['usuario_id'] = usuario.UsuarioId
                session['usuario_nome'] = usuario.Nome

                cursor.execute("UPDATE Usuarios SET UltimoAcesso = ? WHERE UsuarioId = ?",
                               (datetime.now(), usuario.UsuarioId))

                flash(f'Bem-vindo, {usuario.Nome}!', 'success')
                next_page = safe_next_url(request.args.get('next'))
                return redirect(next_page or url_for('dashboard.index'))

        flash('Usuário ou senha inválidos.', 'danger')

    return render_template('admin/login.html')


@admin_bp.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        username = (request.form.get('usuario') or '').strip()
        senha = request.form.get('senha') or ''
        confirmar_senha = request.form.get('confirmar_senha') or ''

        if not nome or not username or not senha:
            flash('Preencha todos os campos obrigatórios.', 'danger')
            return redirect(url_for('admin.cadastro'))

        if senha != confirmar_senha:
            flash('As senhas informadas não conferem.', 'danger')
            return redirect(url_for('admin.cadastro'))

        with get_db_cursor() as cursor:
            cursor.execute("SELECT UsuarioId FROM Usuarios WHERE Username = ?", (username,))
            if cursor.fetchone():
                flash('Este usuário já está cadastrado.', 'warning')
                return redirect(url_for('admin.cadastro'))

            cursor.execute("""
                INSERT INTO Usuarios (Nome, Username, SenhaHash)
                VALUES (?, ?, ?)
            """, (nome, username, generate_password_hash(senha)))

            cursor.execute("SELECT UsuarioId, Nome FROM Usuarios WHERE Username = ?", (username,))
            usuario = cursor.fetchone()

        user = User(usuario.UsuarioId, usuario.Nome, username)
        login_user(user)
        session['admin_logado'] = True
        session['usuario_id'] = usuario.UsuarioId
        session['usuario_nome'] = usuario.Nome

        flash('Conta criada com sucesso. Bem-vindo à plataforma!', 'success')
        return redirect(url_for('financas.dashboard'))

    return render_template('admin/cadastro.html')

@admin_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('main.index'))

@admin_bp.route('/experiencia/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_experiencia(id):
    if request.method == 'POST':
        nome_empresa = request.form.get('nome_empresa')
        cargo = request.form.get('cargo')
        resumo = request.form.get('resumo_curto')
        data_inicio = request.form.get('data_inicio')
        data_fim = request.form.get('data_fim') or None

        with get_db_cursor() as cursor:
            cursor.execute("SELECT EmpresaId FROM Empresa WHERE NomeEmpresa = ?", (nome_empresa,))
            empresa = cursor.fetchone()
            if not empresa:
                flash('Empresa selecionada não encontrada.', 'danger')
                return redirect(url_for('admin.editar_experiencia', id=id))

            cursor.execute("""
                UPDATE ExperienciaProfissional
                SET EmpresaId = ?, Cargo = ?, ResumoCurto = ?, DataInicio = ?, DataFim = ?
                WHERE ExperienciaId = ?
            """, (empresa[0], cargo, resumo, data_inicio, data_fim, id))

        flash('Experiência e empresa atualizadas!', 'success')
        return redirect(url_for('curriculo.especialista'))

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT E.*, Em.NomeEmpresa
            FROM ExperienciaProfissional E
            JOIN Empresa Em ON E.EmpresaId = Em.EmpresaId
            WHERE E.ExperienciaId = ?
        """, (id,))
        exp = cursor.fetchone()

        cursor.execute("SELECT NomeEmpresa FROM Empresa ORDER BY NomeEmpresa")
        empresas = [row[0] for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM ExperienciaDetalhe WHERE ExperienciaId = ?", (id,))
        detalhes = cursor.fetchall()

    nome_empresa_atual = exp.NomeEmpresa if exp else ""
    return render_template('admin/form_experiencia.html',
                           exp=exp, empresas=empresas, detalhes=detalhes,
                           nome_empresa_atual=nome_empresa_atual)

@admin_bp.route('/experiencia/detalhe/adicionar/<int:exp_id>', methods=['POST'])
@login_required
def adicionar_conquista(exp_id):
    descricao = request.form.get('descricao_conquista')
    if descricao:
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO ExperienciaDetalhe (ExperienciaId, DescricaoConquista)
                VALUES (?, ?)
            """, (exp_id, descricao))
        flash('Conquista adicionada com sucesso!', 'success')

    return redirect(url_for('admin.editar_experiencia', id=exp_id))

@admin_bp.route('/experiencia/detalhe/excluir/<int:detalhe_id>/<int:exp_id>', methods=['POST'])
@login_required
def excluir_conquista(detalhe_id, exp_id):
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM ExperienciaDetalhe WHERE ExperienciaDetalheId = ?", (detalhe_id,))

    flash('Conquista removida.', 'info')
    return redirect(url_for('admin.editar_experiencia', id=exp_id))

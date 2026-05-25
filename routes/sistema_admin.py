from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from database import get_db_cursor
from helpers.admin_auth import admin_required


ADMIN_MODULE_CODES = {'admin', 'sistema_admin', 'system_admin', 'administracao'}
WORKSPACE_TIPOS = ('pessoal', 'familia', 'empresa')
NIVEIS_ACESSO_WORKSPACE = ('dono', 'editor', 'visualizador')
ADMIN_TIPOS = ('master', 'suporte')

sistema_admin_bp = Blueprint(
    'sistema_admin',
    __name__,
    url_prefix='/admin/sistema',
)


@sistema_admin_bp.route('')
@sistema_admin_bp.route('/', strict_slashes=False)
@admin_required
def index():
    cards = [
        {
            'titulo': 'Usu&aacute;rios',
            'descricao': 'Gerencie contas, perfis administrativos e acessos.',
            'icone': 'bi-people',
            'url': url_for('sistema_admin.usuarios'),
        },
        {
            'titulo': 'M&oacute;dulos',
            'descricao': 'Controle quais recursos ficam dispon&iacute;veis no sistema.',
            'icone': 'bi-grid-3x3-gap',
            'url': None,
        },
        {
            'titulo': 'Fam&iacute;lias/Workspaces',
            'descricao': 'Acompanhe agrupamentos familiares e compartilhamentos.',
            'icone': 'bi-diagram-3',
            'url': url_for('sistema_admin.workspaces'),
        },
        {
            'titulo': 'Logs de notifica&ccedil;&otilde;es',
            'descricao': 'Consulte hist&oacute;rico de envios e falhas de notifica&ccedil;&atilde;o.',
            'icone': 'bi-bell',
            'url': url_for('sistema_admin.notificacao_logs'),
        },
    ]
    return render_template('sistema_admin/index.html', cards=cards)


def _coluna_is_admin_existe(cursor):
    cursor.execute("SELECT COL_LENGTH('dbo.Usuarios', 'IsAdmin')")
    coluna = cursor.fetchone()
    return bool(coluna and coluna[0] is not None)


def _coluna_admin_tipo_existe(cursor):
    cursor.execute("SELECT COL_LENGTH('dbo.Usuarios', 'AdminTipo')")
    coluna = cursor.fetchone()
    return bool(coluna and coluna[0] is not None)


def _usuario_logado_eh_master(cursor):
    if not _coluna_is_admin_existe(cursor) or not _coluna_admin_tipo_existe(cursor):
        return False

    cursor.execute("""
        SELECT TOP 1 1
        FROM dbo.Usuarios
        WHERE UsuarioId = ?
          AND ISNULL(IsAdmin, 0) = 1
          AND AdminTipo = 'master'
    """, (int(current_user.get_id()),))
    return cursor.fetchone() is not None


def _exigir_admin_master(cursor):
    if _usuario_logado_eh_master(cursor):
        return None

    flash('Acesso negado. Area restrita a administradores master.', 'danger')
    return redirect(url_for('sistema_admin.index'))


def _modulo_administracao(modulo):
    return (modulo.Codigo or '').lower() in ADMIN_MODULE_CODES


def _usuarios_para_select(cursor):
    cursor.execute("""
        SELECT UsuarioId, Nome, Username
        FROM dbo.Usuarios
        ORDER BY Nome, Username
    """)
    return cursor.fetchall()


def _obter_workspace(cursor, workspace_id):
    cursor.execute("""
        SELECT W.WorkspaceId, W.Nome, W.Tipo, W.DonoUsuarioId, ISNULL(W.Ativo, 1) AS Ativo,
               U.Nome AS DonoNome, U.Username AS DonoUsername
        FROM dbo.APP_Workspaces W
        JOIN dbo.Usuarios U
            ON U.UsuarioId = W.DonoUsuarioId
        WHERE W.WorkspaceId = ?
    """, (workspace_id,))
    return cursor.fetchone()


def _usuario_existe(cursor, usuario_id):
    cursor.execute("SELECT TOP 1 1 FROM dbo.Usuarios WHERE UsuarioId = ?", (usuario_id,))
    return cursor.fetchone() is not None


def _workspace_pessoal_duplicado(cursor, dono_usuario_id, workspace_id=None):
    params = [dono_usuario_id]
    filtro_workspace = ''
    if workspace_id:
        filtro_workspace = 'AND WorkspaceId <> ?'
        params.append(workspace_id)

    cursor.execute(f"""
        SELECT TOP 1 1
        FROM dbo.APP_Workspaces
        WHERE DonoUsuarioId = ?
          AND Tipo = 'pessoal'
          {filtro_workspace}
    """, tuple(params))
    return cursor.fetchone() is not None


def _salvar_membro_workspace(cursor, workspace_id, usuario_id, nivel_acesso, ativo):
    cursor.execute("""
        SELECT WorkspaceUsuarioId
        FROM dbo.APP_WorkspaceUsuarios
        WHERE WorkspaceId = ? AND UsuarioId = ?
    """, (workspace_id, usuario_id))
    vinculo = cursor.fetchone()

    if vinculo:
        cursor.execute("""
            UPDATE dbo.APP_WorkspaceUsuarios
            SET NivelAcesso = ?, Ativo = ?
            WHERE WorkspaceUsuarioId = ?
        """, (nivel_acesso, 1 if ativo else 0, vinculo.WorkspaceUsuarioId))
        return

    cursor.execute("""
        INSERT INTO dbo.APP_WorkspaceUsuarios (WorkspaceId, UsuarioId, NivelAcesso, Ativo)
        VALUES (?, ?, ?, ?)
    """, (workspace_id, usuario_id, nivel_acesso, 1 if ativo else 0))


def _dados_workspace_form():
    nome = (request.form.get('nome') or '').strip()
    tipo = (request.form.get('tipo') or 'familia').strip().lower()
    dono_usuario_id = request.form.get('dono_usuario_id', type=int)
    ativo = request.form.get('ativo') == '1'

    if tipo not in WORKSPACE_TIPOS:
        tipo = 'familia'

    return nome, tipo, dono_usuario_id, ativo


@sistema_admin_bp.route('/usuarios')
@admin_required
def usuarios():
    with get_db_cursor() as cursor:
        campo_admin = 'ISNULL(IsAdmin, 0)' if _coluna_is_admin_existe(cursor) else 'CAST(0 AS BIT)'
        cursor.execute(f"""
            SELECT UsuarioId, Nome, Username, {campo_admin} AS IsAdmin
            FROM dbo.Usuarios
            ORDER BY Nome, Username
        """)
        usuarios_lista = cursor.fetchall()

        cursor.execute("""
            SELECT UM.UsuarioId, M.Nome, M.Codigo
            FROM dbo.APP_UsuarioModulos UM
            JOIN dbo.APP_Modulos M
                ON M.ModuloId = UM.ModuloId
            WHERE ISNULL(UM.Ativo, 1) = 1
              AND ISNULL(M.Ativo, 1) = 1
            ORDER BY M.Nome
        """)
        modulos_por_usuario = {}
        for item in cursor.fetchall():
            modulos_por_usuario.setdefault(item.UsuarioId, []).append(item)

    return render_template(
        'sistema_admin/usuarios.html',
        usuarios=usuarios_lista,
        modulos_por_usuario=modulos_por_usuario,
    )


@sistema_admin_bp.route('/usuarios/<int:usuario_id>/modulos', methods=['GET', 'POST'])
@admin_required
def usuario_modulos(usuario_id):
    usuario_atual_id = int(current_user.get_id())

    with get_db_cursor() as cursor:
        campo_admin = 'ISNULL(IsAdmin, 0)' if _coluna_is_admin_existe(cursor) else 'CAST(0 AS BIT)'
        cursor.execute(f"""
            SELECT UsuarioId, Nome, Username, {campo_admin} AS IsAdmin
            FROM dbo.Usuarios
            WHERE UsuarioId = ?
        """, (usuario_id,))
        usuario = cursor.fetchone()

        if not usuario:
            flash('Usuario nao encontrado.', 'warning')
            return redirect(url_for('sistema_admin.usuarios'))

        cursor.execute("""
            SELECT ModuloId, Codigo, Nome, Descricao, ISNULL(Ativo, 1) AS Ativo
            FROM dbo.APP_Modulos
            ORDER BY Nome
        """)
        modulos = cursor.fetchall()

        if request.method == 'POST':
            modulos_selecionados = {
                int(valor)
                for valor in request.form.getlist('modulos')
                if valor.isdigit()
            }
            editando_proprio_usuario = usuario_id == usuario_atual_id
            preservou_admin = False

            for modulo in modulos:
                ativo = modulo.ModuloId in modulos_selecionados
                if editando_proprio_usuario and _modulo_administracao(modulo):
                    ativo = True
                    preservou_admin = modulo.ModuloId not in modulos_selecionados

                cursor.execute("""
                    UPDATE dbo.APP_UsuarioModulos
                    SET Ativo = ?
                    WHERE UsuarioId = ? AND ModuloId = ?
                """, (1 if ativo else 0, usuario_id, modulo.ModuloId))

                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO dbo.APP_UsuarioModulos (UsuarioId, ModuloId, Ativo)
                        VALUES (?, ?, ?)
                    """, (usuario_id, modulo.ModuloId, 1 if ativo else 0))

            if preservou_admin:
                flash('O modulo de administracao do seu proprio usuario foi mantido ativo.', 'warning')
            else:
                flash('Modulos do usuario atualizados com sucesso.', 'success')

            return redirect(url_for('sistema_admin.usuarios'))

        cursor.execute("""
            SELECT ModuloId, ISNULL(Ativo, 1) AS Ativo
            FROM dbo.APP_UsuarioModulos
            WHERE UsuarioId = ?
        """, (usuario_id,))
        modulos_usuario = {
            item.ModuloId: bool(item.Ativo)
            for item in cursor.fetchall()
        }

    return render_template(
        'sistema_admin/usuario_modulos.html',
        usuario=usuario,
        modulos=modulos,
        modulos_usuario=modulos_usuario,
        editando_proprio_usuario=usuario_id == usuario_atual_id,
        codigos_modulos_admin=ADMIN_MODULE_CODES,
    )


@sistema_admin_bp.route('/admins', methods=['GET', 'POST'])
@admin_required
def admins():
    usuario_atual_id = int(current_user.get_id())

    with get_db_cursor() as cursor:
        bloqueio = _exigir_admin_master(cursor)
        if bloqueio:
            return bloqueio

        if request.method == 'POST':
            usuarios_admin = {
                int(valor)
                for valor in request.form.getlist('is_admin')
                if valor.isdigit()
            }
            tipos_por_usuario = {}

            cursor.execute("SELECT UsuarioId FROM dbo.Usuarios")
            usuarios_ids = [int(item.UsuarioId) for item in cursor.fetchall()]

            tentou_remover_proprio_master = False
            if usuario_atual_id not in usuarios_admin:
                tentou_remover_proprio_master = True

            for usuario_id in usuarios_ids:
                admin_tipo = (request.form.get(f'admin_tipo_{usuario_id}') or 'suporte').strip().lower()
                if admin_tipo not in ADMIN_TIPOS:
                    admin_tipo = 'suporte'

                if usuario_id == usuario_atual_id and admin_tipo != 'master':
                    tentou_remover_proprio_master = True

                tipos_por_usuario[usuario_id] = admin_tipo

            if tentou_remover_proprio_master:
                flash('Bloqueado: voce nao pode remover seu proprio acesso master.', 'warning')

            for usuario_id in usuarios_ids:
                is_admin = usuario_id in usuarios_admin
                admin_tipo = tipos_por_usuario[usuario_id] if is_admin else None

                if usuario_id == usuario_atual_id:
                    is_admin = True
                    admin_tipo = 'master'

                cursor.execute("""
                    UPDATE dbo.Usuarios
                    SET IsAdmin = ?, AdminTipo = ?
                    WHERE UsuarioId = ?
                """, (1 if is_admin else 0, admin_tipo, usuario_id))

            if not tentou_remover_proprio_master:
                flash('Administradores atualizados com sucesso.', 'success')

            return redirect(url_for('sistema_admin.admins'))

        cursor.execute("""
            SELECT UsuarioId, Nome, Username, ISNULL(IsAdmin, 0) AS IsAdmin, AdminTipo
            FROM dbo.Usuarios
            ORDER BY IsAdmin DESC, AdminTipo, Nome, Username
        """)
        usuarios_lista = cursor.fetchall()

    return render_template(
        'sistema_admin/admins.html',
        usuarios=usuarios_lista,
        admin_tipos=ADMIN_TIPOS,
        usuario_atual_id=usuario_atual_id,
    )


@sistema_admin_bp.route('/workspaces')
@admin_required
def workspaces():
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT W.WorkspaceId, W.Nome, W.Tipo, W.DonoUsuarioId, ISNULL(W.Ativo, 1) AS Ativo,
                   U.Nome AS DonoNome, U.Username AS DonoUsername,
                   COUNT(CASE WHEN WU.WorkspaceUsuarioId IS NOT NULL AND ISNULL(WU.Ativo, 1) = 1 THEN 1 END) AS TotalMembros
            FROM dbo.APP_Workspaces W
            JOIN dbo.Usuarios U
                ON U.UsuarioId = W.DonoUsuarioId
            LEFT JOIN dbo.APP_WorkspaceUsuarios WU
                ON WU.WorkspaceId = W.WorkspaceId
            GROUP BY W.WorkspaceId, W.Nome, W.Tipo, W.DonoUsuarioId, W.Ativo, U.Nome, U.Username
            ORDER BY W.Ativo DESC, W.Tipo, W.Nome
        """)
        workspaces_lista = cursor.fetchall()

    return render_template(
        'sistema_admin/workspaces.html',
        workspaces=workspaces_lista,
    )


@sistema_admin_bp.route('/workspaces/novo', methods=['GET', 'POST'])
@admin_required
def workspace_novo():
    with get_db_cursor() as cursor:
        usuarios_lista = _usuarios_para_select(cursor)

        if request.method == 'POST':
            nome, tipo, dono_usuario_id, ativo = _dados_workspace_form()

            if not nome:
                flash('Informe o nome do workspace.', 'danger')
                return render_template(
                    'sistema_admin/workspace_form.html',
                    workspace=None,
                    usuarios=usuarios_lista,
                    tipos=WORKSPACE_TIPOS,
                    form={'nome': nome, 'tipo': tipo, 'dono_usuario_id': dono_usuario_id, 'ativo': ativo},
                )

            if not dono_usuario_id or not _usuario_existe(cursor, dono_usuario_id):
                flash('Selecione um dono valido para o workspace.', 'danger')
                return render_template(
                    'sistema_admin/workspace_form.html',
                    workspace=None,
                    usuarios=usuarios_lista,
                    tipos=WORKSPACE_TIPOS,
                    form={'nome': nome, 'tipo': tipo, 'dono_usuario_id': dono_usuario_id, 'ativo': ativo},
                )

            if tipo == 'pessoal' and _workspace_pessoal_duplicado(cursor, dono_usuario_id):
                flash('Este usuario ja possui um workspace pessoal.', 'danger')
                return render_template(
                    'sistema_admin/workspace_form.html',
                    workspace=None,
                    usuarios=usuarios_lista,
                    tipos=WORKSPACE_TIPOS,
                    form={'nome': nome, 'tipo': tipo, 'dono_usuario_id': dono_usuario_id, 'ativo': ativo},
                )

            cursor.execute("""
                INSERT INTO dbo.APP_Workspaces (Nome, Tipo, DonoUsuarioId, Ativo)
                VALUES (?, ?, ?, ?)
            """, (nome[:100], tipo, dono_usuario_id, 1 if ativo else 0))
            cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
            workspace_id = int(cursor.fetchone()[0])
            _salvar_membro_workspace(cursor, workspace_id, dono_usuario_id, 'dono', True)

            flash('Workspace criado com sucesso.', 'success')
            return redirect(url_for('sistema_admin.workspace_membros', workspace_id=workspace_id))

    return render_template(
        'sistema_admin/workspace_form.html',
        workspace=None,
        usuarios=usuarios_lista,
        tipos=WORKSPACE_TIPOS,
        form={'nome': '', 'tipo': 'familia', 'dono_usuario_id': None, 'ativo': True},
    )


@sistema_admin_bp.route('/workspaces/<int:workspace_id>/editar', methods=['GET', 'POST'])
@admin_required
def workspace_editar(workspace_id):
    with get_db_cursor() as cursor:
        workspace = _obter_workspace(cursor, workspace_id)
        if not workspace:
            flash('Workspace nao encontrado.', 'warning')
            return redirect(url_for('sistema_admin.workspaces'))

        usuarios_lista = _usuarios_para_select(cursor)

        if request.method == 'POST':
            nome, tipo, dono_usuario_id, ativo = _dados_workspace_form()

            if not nome:
                flash('Informe o nome do workspace.', 'danger')
                return render_template(
                    'sistema_admin/workspace_form.html',
                    workspace=workspace,
                    usuarios=usuarios_lista,
                    tipos=WORKSPACE_TIPOS,
                    form={'nome': nome, 'tipo': tipo, 'dono_usuario_id': dono_usuario_id, 'ativo': ativo},
                )

            if not dono_usuario_id or not _usuario_existe(cursor, dono_usuario_id):
                flash('Selecione um dono valido para o workspace.', 'danger')
                return render_template(
                    'sistema_admin/workspace_form.html',
                    workspace=workspace,
                    usuarios=usuarios_lista,
                    tipos=WORKSPACE_TIPOS,
                    form={'nome': nome, 'tipo': tipo, 'dono_usuario_id': dono_usuario_id, 'ativo': ativo},
                )

            if tipo == 'pessoal' and _workspace_pessoal_duplicado(cursor, dono_usuario_id, workspace_id):
                flash('Este usuario ja possui outro workspace pessoal.', 'danger')
                return render_template(
                    'sistema_admin/workspace_form.html',
                    workspace=workspace,
                    usuarios=usuarios_lista,
                    tipos=WORKSPACE_TIPOS,
                    form={'nome': nome, 'tipo': tipo, 'dono_usuario_id': dono_usuario_id, 'ativo': ativo},
                )

            cursor.execute("""
                UPDATE dbo.APP_Workspaces
                SET Nome = ?, Tipo = ?, DonoUsuarioId = ?, Ativo = ?
                WHERE WorkspaceId = ?
            """, (nome[:100], tipo, dono_usuario_id, 1 if ativo else 0, workspace_id))
            _salvar_membro_workspace(cursor, workspace_id, dono_usuario_id, 'dono', True)

            flash('Workspace atualizado com sucesso.', 'success')
            return redirect(url_for('sistema_admin.workspaces'))

    return render_template(
        'sistema_admin/workspace_form.html',
        workspace=workspace,
        usuarios=usuarios_lista,
        tipos=WORKSPACE_TIPOS,
        form={
            'nome': workspace.Nome,
            'tipo': workspace.Tipo,
            'dono_usuario_id': workspace.DonoUsuarioId,
            'ativo': bool(workspace.Ativo),
        },
    )


@sistema_admin_bp.route('/workspaces/<int:workspace_id>/membros', methods=['GET', 'POST'])
@admin_required
def workspace_membros(workspace_id):
    with get_db_cursor() as cursor:
        workspace = _obter_workspace(cursor, workspace_id)
        if not workspace:
            flash('Workspace nao encontrado.', 'warning')
            return redirect(url_for('sistema_admin.workspaces'))

        usuarios_lista = _usuarios_para_select(cursor)

        cursor.execute("""
            SELECT UsuarioId, NivelAcesso, ISNULL(Ativo, 1) AS Ativo
            FROM dbo.APP_WorkspaceUsuarios
            WHERE WorkspaceId = ?
        """, (workspace_id,))
        membros = {
            item.UsuarioId: {
                'nivel': item.NivelAcesso,
                'ativo': bool(item.Ativo),
            }
            for item in cursor.fetchall()
        }

        if request.method == 'POST':
            usuarios_selecionados = {
                int(valor)
                for valor in request.form.getlist('usuarios')
                if valor.isdigit()
            }

            if workspace.DonoUsuarioId not in usuarios_selecionados:
                flash('Nao e permitido remover o dono principal sem antes trocar o dono do workspace.', 'danger')
                return redirect(url_for('sistema_admin.workspace_membros', workspace_id=workspace_id))

            for usuario in usuarios_lista:
                usuario_id = usuario.UsuarioId
                ativo = usuario_id in usuarios_selecionados
                nivel = (request.form.get(f'nivel_{usuario_id}') or 'visualizador').strip().lower()
                if nivel not in NIVEIS_ACESSO_WORKSPACE:
                    nivel = 'visualizador'

                if usuario_id == workspace.DonoUsuarioId:
                    ativo = True
                    nivel = 'dono'

                if ativo or usuario_id in membros:
                    _salvar_membro_workspace(cursor, workspace_id, usuario_id, nivel, ativo)

            flash('Membros do workspace atualizados com sucesso.', 'success')
            return redirect(url_for('sistema_admin.workspaces'))

    return render_template(
        'sistema_admin/workspace_membros.html',
        workspace=workspace,
        usuarios=usuarios_lista,
        membros=membros,
        niveis=NIVEIS_ACESSO_WORKSPACE,
    )

@sistema_admin_bp.route('/notificacoes')
@admin_required
def notificacao_logs():
    status = (request.args.get('status') or '').strip()
    usuario_id = request.args.get('usuario_id', type=int)

    filtros = []
    params = []

    if status:
        filtros.append("L.Status = ?")
        params.append(status)

    if usuario_id:
        filtros.append("L.UsuarioId = ?")
        params.append(usuario_id)

    where_sql = ""
    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT UsuarioId, Nome, Username
            FROM Usuarios
            ORDER BY Nome
        """)
        usuarios = cursor.fetchall()

        cursor.execute("""
            SELECT DISTINCT Status
            FROM APP_NotificacaoLogs
            WHERE Status IS NOT NULL
            ORDER BY Status
        """)
        status_lista = cursor.fetchall()

        query = f"""
            SELECT TOP 200
                L.NotificacaoLogId,
                L.UsuarioId,
                U.Nome AS UsuarioNome,
                U.Username,
                L.Tipo,
                L.EmailDestino,
                L.Assunto,
                L.Status,
                L.MensagemErro,
                L.DataEnvio
            FROM APP_NotificacaoLogs L
            LEFT JOIN Usuarios U
                ON U.UsuarioId = L.UsuarioId
            {where_sql}
            ORDER BY L.DataEnvio DESC
        """

        cursor.execute(query, tuple(params))
        logs = cursor.fetchall()

    return render_template(
        'sistema_admin/notificacao_logs.html',
        logs=logs,
        usuarios=usuarios,
        status_lista=status_lista,
        filtro_status=status,
        filtro_usuario_id=usuario_id
    )
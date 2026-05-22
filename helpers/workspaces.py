def usuarios_visiveis_financeiro(cursor, usuario_id):
    try:
        usuario_id = int(usuario_id)
    except (TypeError, ValueError):
        return []

    try:
        cursor.execute("""
            SELECT
                OBJECT_ID('dbo.APP_Workspaces', 'U') AS WorkspacesId,
                OBJECT_ID('dbo.APP_WorkspaceUsuarios', 'U') AS WorkspaceUsuariosId
        """)
        row = cursor.fetchone()
        if not row or not row[0] or not row[1]:
            return [usuario_id]

        cursor.execute("""
            SELECT DISTINCT WUOutro.UsuarioId
            FROM APP_WorkspaceUsuarios WUEu
            JOIN APP_Workspaces W
                ON W.WorkspaceId = WUEu.WorkspaceId
            JOIN APP_WorkspaceUsuarios WUOutro
                ON WUOutro.WorkspaceId = WUEu.WorkspaceId
            WHERE WUEu.UsuarioId = ?
              AND ISNULL(WUEu.Ativo, 1) = 1
              AND ISNULL(WUOutro.Ativo, 1) = 1
              AND ISNULL(W.Ativo, 1) = 1
            ORDER BY WUOutro.UsuarioId
        """, (usuario_id,))
        usuarios = [int(row[0]) for row in cursor.fetchall()]
        return usuarios or [usuario_id]
    except Exception:
        return [usuario_id]

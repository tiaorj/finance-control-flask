from flask import has_request_context
from flask_login import current_user

from database import get_db_cursor


def _tabelas_modulos_existem(cursor):
    cursor.execute("""
        SELECT
            OBJECT_ID('dbo.APP_UsuarioModulos', 'U') AS UsuarioModulosId,
            OBJECT_ID('dbo.APP_Modulos', 'U') AS ModulosId
    """)
    row = cursor.fetchone()
    return bool(row and row[0] and row[1])


def usuario_tem_modulo(codigo):
    """Retorna se o usuario atual tem acesso ativo ao modulo informado."""
    if not codigo or not has_request_context():
        return True

    if not current_user.is_authenticated:
        return True

    try:
        usuario_id = int(current_user.get_id())
    except (TypeError, ValueError):
        return True

    with get_db_cursor() as cursor:
        if not _tabelas_modulos_existem(cursor):
            return True

        cursor.execute("""
            SELECT TOP 1 1
            FROM APP_UsuarioModulos UM
            JOIN APP_Modulos M
                ON M.ModuloId = UM.ModuloId
            WHERE UM.UsuarioId = ?
              AND M.Codigo = ?
              AND ISNULL(UM.Ativo, 1) = 1
              AND ISNULL(M.Ativo, 1) = 1
        """, (usuario_id, codigo.strip().lower()))
        return cursor.fetchone() is not None

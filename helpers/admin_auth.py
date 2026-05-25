from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user, login_required

from database import get_db_cursor


def usuario_eh_admin():
    if not current_user.is_authenticated:
        return False

    try:
        usuario_id = int(current_user.get_id())
    except (TypeError, ValueError):
        return False

    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COL_LENGTH('dbo.Usuarios', 'IsAdmin')")
            coluna = cursor.fetchone()
            if not coluna or coluna[0] is None:
                return False

            cursor.execute("""
                SELECT ISNULL(IsAdmin, 0)
                FROM dbo.Usuarios
                WHERE UsuarioId = ?
            """, (usuario_id,))
            usuario = cursor.fetchone()
            return bool(usuario and usuario[0])
    except Exception:
        return False


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(*args, **kwargs):
        if not usuario_eh_admin():
            flash('Acesso negado. Area restrita a administradores.', 'danger')
            return redirect(url_for('dashboard.index'))

        return view_func(*args, **kwargs)

    return wrapper

from flask import Blueprint, render_template
from database import get_db_cursor
from routes.admin import login_required

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/admin')

@dashboard_bp.route('/dashboard')
@login_required
def index():
    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM ExperienciaProfissional")
        total_exp = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Projeto")
        total_proj = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM FormacaoAcademica")
        total_form = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Certificacoes")
        total_cert = cursor.fetchone()[0]

        cursor.execute("""
            SELECT TOP 3 Cargo, NomeEmpresa
            FROM ExperienciaProfissional E
            JOIN Empresa Em ON E.EmpresaId = Em.EmpresaId
            ORDER BY E.ExperienciaId DESC
        """)
        ultimas_atividades = cursor.fetchall()

    return render_template('admin/dashboard.html',
                           total_exp=total_exp,
                           total_proj=total_proj,
                           total_cert=total_cert,
                           total_form=total_form,
                           atividades=ultimas_atividades)

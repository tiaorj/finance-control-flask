import re
import unicodedata
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_cursor
from routes.admin import login_required

experiencias_bp = Blueprint('experiencias_admin', __name__, url_prefix='/admin/experiencias')

def slugify(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '_', text)

@experiencias_bp.route('/')
@login_required
def lista():
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT E.ExperienciaId, Em.NomeEmpresa, E.Cargo,
                   FORMAT(E.DataInicio, 'MM/yyyy') as Inicio,
                   ISNULL(FORMAT(E.DataFim, 'MM/yyyy'), 'Atual') as Fim
            FROM ExperienciaProfissional E
            JOIN Empresa Em ON E.EmpresaId = Em.EmpresaId
            ORDER BY E.DataInicio DESC
        """)
        experiencias = cursor.fetchall()

    return render_template('admin/experiencias_lista.html', experiencias=experiencias)

@experiencias_bp.route('/form', defaults={'id': None}, methods=['GET', 'POST'])
@experiencias_bp.route('/form/<int:id>', methods=['GET', 'POST'])
@login_required
def form(id):
    if request.method == 'POST':
        nome_empresa = request.form.get('nome_empresa').strip()
        cargo = request.form.get('cargo')
        resumo = request.form.get('resumo_curto')
        data_inicio = request.form.get('data_inicio')
        data_fim = request.form.get('data_fim') or None
        conquistas_enviadas = request.form.getlist('conquistas[]')

        with get_db_cursor() as cursor:
            cursor.execute("SELECT EmpresaId FROM Empresa WHERE NomeEmpresa = ?", (nome_empresa,))
            row_empresa = cursor.fetchone()

            if row_empresa:
                empresa_id = row_empresa[0]
            else:
                novo_slug = slugify(nome_empresa)
                cursor.execute("INSERT INTO Empresa (NomeEmpresa, Slug) OUTPUT INSERTED.EmpresaId VALUES (?, ?)",
                               (nome_empresa, novo_slug))
                empresa_id = cursor.fetchone()[0]

            if id:
                cursor.execute("""
                    UPDATE ExperienciaProfissional
                    SET EmpresaId=?, Cargo=?, ResumoCurto=?, DataInicio=?, DataFim=?
                    WHERE ExperienciaId=?
                """, (empresa_id, cargo, resumo, data_inicio, data_fim, id))
                exp_id = id
                cursor.execute("DELETE FROM ExperienciaDetalhe WHERE ExperienciaId = ?", (id,))
            else:
                cursor.execute("""
                    INSERT INTO ExperienciaProfissional (EmpresaId, Cargo, ResumoCurto, DataInicio, DataFim)
                    OUTPUT INSERTED.ExperienciaId
                    VALUES (?, ?, ?, ?, ?)
                """, (empresa_id, cargo, resumo, data_inicio, data_fim))
                exp_id = cursor.fetchone()[0]

            for desc in conquistas_enviadas:
                if desc.strip():
                    cursor.execute("INSERT INTO ExperienciaDetalhe (ExperienciaId, DescricaoConquista) VALUES (?, ?)",
                                   (exp_id, desc.strip()))

        flash('Experiência salva com sucesso!', 'success')
        return redirect(url_for('experiencias_admin.lista'))

    with get_db_cursor() as cursor:
        cursor.execute("SELECT NomeEmpresa FROM Empresa ORDER BY NomeEmpresa")
        empresas = [row[0] for row in cursor.fetchall()]

        exp = None
        detalhes = []
        nome_empresa_atual = ""

        if id:
            cursor.execute("""
                SELECT E.Cargo, E.ResumoCurto, E.DataInicio, E.DataFim, Em.NomeEmpresa
                FROM ExperienciaProfissional E
                JOIN Empresa Em ON E.EmpresaId = Em.EmpresaId
                WHERE E.ExperienciaId = ?
            """, (id,))
            row = cursor.fetchone()
            if row:
                exp = {
                    'Cargo': row[0],
                    'ResumoCurto': row[1],
                    'DataInicio': row[2],
                    'DataFim': row[3]
                }
                nome_empresa_atual = row[4]

                cursor.execute("SELECT DescricaoConquista FROM ExperienciaDetalhe WHERE ExperienciaId = ?", (id,))
                detalhes = [r[0] for r in cursor.fetchall()]

    return render_template('admin/form_experiencia.html',
                           exp=exp, empresas=empresas, detalhes=detalhes,
                           nome_empresa_atual=nome_empresa_atual)

@experiencias_bp.route('/trajetoria')
def trajetoria_publica():
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT E.*, Em.NomeEmpresa
            FROM ExperienciaProfissional E
            JOIN Empresa Em ON E.EmpresaId = Em.EmpresaId
            ORDER BY
                CASE WHEN E.DataFim IS NULL THEN 0 ELSE 1 END,
                E.DataFim DESC,
                E.DataInicio DESC
        """)
        experiencias_raw = cursor.fetchall()

        experiencias = []
        for exp in experiencias_raw:
            cursor.execute("SELECT DescricaoConquista FROM ExperienciaDetalhe WHERE ExperienciaId = ?", (exp.ExperienciaId,))
            conquistas = [d[0] for d in cursor.fetchall()]

            inicio = datetime.strptime(exp.DataInicio[:10], '%Y-%m-%d') if isinstance(exp.DataInicio, str) else exp.DataInicio
            fim = None
            if exp.DataFim:
                fim = datetime.strptime(exp.DataFim[:10], '%Y-%m-%d') if isinstance(exp.DataFim, str) else exp.DataFim

            experiencias.append({
                'ExperienciaId': exp.ExperienciaId,
                'Cargo': exp.Cargo,
                'Empresa': exp.NomeEmpresa,
                'Resumo': exp.ResumoCurto,
                'Inicio': inicio,
                'Fim': fim,
                'Conquistas': conquistas
            })

    return render_template('trajetoria.html', experiencias=experiencias)

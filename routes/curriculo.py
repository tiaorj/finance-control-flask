from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, render_template, make_response, request, redirect, url_for, flash
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from database import get_db_cursor
from xhtml2pdf import pisa
from io import BytesIO

curriculo_bp = Blueprint('curriculo', __name__)
EXTENSOES_FOTO_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp'}


def tabela_curriculo_perfil_existe(cursor):
    cursor.execute("SELECT OBJECT_ID('dbo.CurriculoPerfil', 'U')")
    row = cursor.fetchone()
    return bool(row and row[0])


def garantir_tabela_curriculo_perfil(cursor):
    cursor.execute("""
        IF OBJECT_ID('dbo.CurriculoPerfil', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.CurriculoPerfil (
                CurriculoPerfilId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                UsuarioId INT NOT NULL UNIQUE,
                NomeExibicao NVARCHAR(150) NOT NULL,
                Cargo NVARCHAR(200) NULL,
                Resumo NVARCHAR(MAX) NULL,
                Localizacao NVARCHAR(150) NULL,
                Telefone NVARCHAR(50) NULL,
                Email NVARCHAR(150) NULL,
                Linkedin NVARCHAR(250) NULL,
                FotoArquivo NVARCHAR(255) NULL,
                DataAtualizacao DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                CONSTRAINT FK_CurriculoPerfil_Usuarios
                    FOREIGN KEY (UsuarioId) REFERENCES dbo.Usuarios(UsuarioId)
            )
        END

        INSERT INTO dbo.CurriculoPerfil (UsuarioId, NomeExibicao)
        SELECT U.UsuarioId, U.Nome
        FROM dbo.Usuarios U
        WHERE NOT EXISTS (
            SELECT 1
            FROM dbo.CurriculoPerfil P
            WHERE P.UsuarioId = U.UsuarioId
        )
    """)


def get_perfil_curriculo(cursor, usuario_id):
    if tabela_curriculo_perfil_existe(cursor):
        cursor.execute("""
            SELECT
                U.Nome AS UsuarioNome,
                P.NomeExibicao,
                P.Cargo,
                P.Resumo,
                P.Localizacao,
                P.Telefone,
                P.Email,
                P.Linkedin,
                P.FotoArquivo
            FROM Usuarios U
            LEFT JOIN CurriculoPerfil P ON P.UsuarioId = U.UsuarioId
            WHERE U.UsuarioId = ?
        """, (usuario_id,))
    else:
        cursor.execute("""
            SELECT Nome AS UsuarioNome
            FROM Usuarios
            WHERE UsuarioId = ?
        """, (usuario_id,))

    row = cursor.fetchone()
    usuario_nome = getattr(row, 'UsuarioNome', None) if row else ''
    nome_exibicao = getattr(row, 'NomeExibicao', None) if row else None

    return {
        'nome': nome_exibicao or usuario_nome or 'Profissional',
        'cargo': getattr(row, 'Cargo', None) or 'Profissional',
        'resumo': getattr(row, 'Resumo', None) or '',
        'localizacao': getattr(row, 'Localizacao', None) or '',
        'telefone': getattr(row, 'Telefone', None) or '',
        'email': getattr(row, 'Email', None) or '',
        'linkedin': getattr(row, 'Linkedin', None) or '',
        'foto_arquivo': getattr(row, 'FotoArquivo', None) or '',
    }


def salvar_foto_perfil(usuario_id):
    foto = request.files.get('foto')
    if not foto or not foto.filename:
        return None

    nome_original = secure_filename(foto.filename)
    extensao = Path(nome_original).suffix.lower()
    if extensao not in EXTENSOES_FOTO_PERMITIDAS:
        raise ValueError('Envie uma foto nos formatos JPG, PNG ou WEBP.')

    pasta_destino = Path(current_app.static_folder) / 'uploads' / 'curriculos'
    pasta_destino.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    nome_arquivo = f'perfil_{usuario_id}_{timestamp}{extensao}'
    foto.save(pasta_destino / nome_arquivo)
    return f'uploads/curriculos/{nome_arquivo}'

# FUNÇÃO AUXILIAR: Centraliza a inteligência de busca
def get_dados_completos_curriculo(usuario_id):
    with get_db_cursor() as cursor:
        perfil = get_perfil_curriculo(cursor, usuario_id)

        # 1. BUSCAR EXPERIÊNCIAS
        cursor.execute("""
            SELECT E.ExperienciaId, Em.NomeEmpresa, E.Cargo, E.ResumoCurto,
                FORMAT(E.DataInicio, 'MM/yyyy') + ' - ' + ISNULL(FORMAT(E.DataFim, 'MM/yyyy'), 'Atual') as Periodo,
                DataInicio
            FROM ExperienciaProfissional E
            JOIN Empresa Em ON E.EmpresaId = Em.EmpresaId
            WHERE E.UsuarioId = ?
            ORDER BY CASE WHEN E.DataFim IS NULL THEN 0 ELSE 1 END, E.DataFim DESC, E.DataInicio DESC
        """, (usuario_id,))
        exps_rows = cursor.fetchall()

        # 2. BUSCAR DETALHES
        cursor.execute("""
            SELECT D.ExperienciaId, D.DescricaoConquista
            FROM ExperienciaDetalhe D
            JOIN ExperienciaProfissional E ON D.ExperienciaId = E.ExperienciaId
            WHERE E.UsuarioId = ?
        """, (usuario_id,))
        detalhes_rows = cursor.fetchall()
        
        detalhes_map = {}
        for d in detalhes_rows:
            if d.ExperienciaId not in detalhes_map:
                detalhes_map[d.ExperienciaId] = []
            detalhes_map[d.ExperienciaId].append(d.DescricaoConquista)

        lista_experiencias = []
        for row in exps_rows:
            lista_experiencias.append({
                'id': row.ExperienciaId,
                'empresa': row.NomeEmpresa,
                'cargo': row.Cargo,
                'resumo': row.ResumoCurto,
                'periodo': row.Periodo,
                'conquistas': detalhes_map.get(row.ExperienciaId, [])
            })

        # 3. HABILIDADES
        cursor.execute("""
            SELECT C.NomeCategoria, STRING_AGG(H.Descricao, ', ') as Itens
            FROM Habilidade H
            JOIN HabilidadeCategoria C ON H.HabilidadeCategoriaId = C.HabilidadeCategoriaId
            WHERE H.UsuarioId = ?
            GROUP BY C.NomeCategoria
        """, (usuario_id,))
        habilidades = cursor.fetchall()

        # 4. FORMAÇÃO
        cursor.execute("""
            SELECT NomeCurso, NomeInstituicao, Descricao, NomeCursoAbreviado, 
            CAST(AnoInicio AS VARCHAR) + ' - ' + ISNULL(CAST(AnoConclusao AS VARCHAR), 'Cursando') as PeriodoFormacao
            FROM FormacaoAcademica
            WHERE UsuarioId = ?
            ORDER BY CASE WHEN AnoConclusao IS NULL THEN 0 ELSE 1 END, AnoConclusao DESC, AnoInicio DESC
        """, (usuario_id,))
        formacao_rows = cursor.fetchall()

        lista_formacao = [{
            'curso': f.NomeCurso,
            'instituicao': f.NomeInstituicao,
            'periodo': f.PeriodoFormacao,
            'Descricao': f.Descricao,
            'NomeCursoAbreviado': f.NomeCursoAbreviado
        } for f in formacao_rows]

        # 5. CERTIFICAÇÕES
        cursor.execute("""
            SELECT Nome, Instituicao, IconeClass, LinkVerificacao
            FROM Certificacoes
            WHERE UsuarioId = ?
        """, (usuario_id,))
        certificados = cursor.fetchall()

    return {
        'perfil': perfil,
        'experiencias': lista_experiencias,
        'habilidades': habilidades,
        'formacao': lista_formacao,
        'certificados': certificados
    }

@curriculo_bp.route('/admin/curriculo/perfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    usuario_id = int(current_user.get_id())

    if request.method == 'POST':
        nome = (request.form.get('nome') or current_user.nome or '').strip()
        cargo = (request.form.get('cargo') or '').strip() or None
        resumo = (request.form.get('resumo') or '').strip() or None
        localizacao = (request.form.get('localizacao') or '').strip() or None
        telefone = (request.form.get('telefone') or '').strip() or None
        email = (request.form.get('email') or '').strip() or None
        linkedin = (request.form.get('linkedin') or '').strip() or None
        foto_arquivo = (request.form.get('foto_arquivo_atual') or '').strip() or None

        if not nome:
            flash('Informe o nome de exibição do currículo.', 'danger')
            return redirect(url_for('curriculo.editar_perfil'))

        try:
            foto_enviada = salvar_foto_perfil(usuario_id)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('curriculo.editar_perfil'))

        if foto_enviada:
            foto_arquivo = foto_enviada

        with get_db_cursor() as cursor:
            garantir_tabela_curriculo_perfil(cursor)
            cursor.execute("SELECT CurriculoPerfilId FROM CurriculoPerfil WHERE UsuarioId = ?", (usuario_id,))
            perfil_existente = cursor.fetchone()

            if perfil_existente:
                cursor.execute("""
                    UPDATE CurriculoPerfil
                    SET NomeExibicao = ?, Cargo = ?, Resumo = ?, Localizacao = ?,
                        Telefone = ?, Email = ?, Linkedin = ?, FotoArquivo = ?,
                        DataAtualizacao = SYSUTCDATETIME()
                    WHERE UsuarioId = ?
                """, (nome, cargo, resumo, localizacao, telefone, email, linkedin, foto_arquivo, usuario_id))
            else:
                cursor.execute("""
                    INSERT INTO CurriculoPerfil
                    (UsuarioId, NomeExibicao, Cargo, Resumo, Localizacao, Telefone, Email, Linkedin, FotoArquivo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, nome, cargo, resumo, localizacao, telefone, email, linkedin, foto_arquivo))

        flash('Perfil do currículo atualizado com sucesso!', 'success')
        return redirect(url_for('curriculo.especialista'))

    with get_db_cursor() as cursor:
        garantir_tabela_curriculo_perfil(cursor)
        perfil = get_perfil_curriculo(cursor, usuario_id)

    return render_template('admin/form_curriculo_perfil.html', perfil=perfil)


@curriculo_bp.route('/especialista')
@login_required
def especialista():
    dados = get_dados_completos_curriculo(int(current_user.get_id()))
    return render_template('especialista.html', **dados)

@curriculo_bp.route('/gerar-pdf')
@login_required
def gerar_pdf():
#@curriculo_bp.route('/debug-html')
#def debug_html():
    dados = get_dados_completos_curriculo(int(current_user.get_id()))
        
    # 2. Renderizar o HTML específico para o PDF
    html = render_template('pdf_template.html', **dados)

    # 3. Converter HTML para PDF
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result, encoding="UTF-8")

    if not pdf.err:
        response = make_response(result.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=curriculo.pdf'
        return response
    
    return "Erro ao gerar PDF", 500
    #return render_template('pdf_template.html', **dados)

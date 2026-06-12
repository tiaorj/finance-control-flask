from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
from database import get_db_cursor
from flask_mail import Message

empresa_bp = Blueprint('empresa', __name__)

MENSAGEM_SUCESSO_IMPLANTACAO_DIRECTOS = (
    "Solicita\u00e7\u00e3o enviada com sucesso. Em breve entraremos em contato "
    "para entender sua opera\u00e7\u00e3o e orientar a implanta\u00e7\u00e3o."
)


def _campo_formulario(nome):
    return (request.form.get(nome) or '').strip()


def _campo_opcional_formulario(nome):
    valor = _campo_formulario(nome)
    return valor or None


def _campo_utm(nome):
    valor = (request.form.get(nome) or request.args.get(nome) or '').strip()
    return valor or None

@empresa_bp.route('/empresa')
def home():
    return render_template('landing.html')

@empresa_bp.route('/projetos')
@login_required
def projetos():
    usuario_id = int(current_user.get_id())
    with get_db_cursor() as cursor:
        # Busca os projetos da nova tabela conforme sua remodelagem
        cursor.execute("""
            SELECT Titulo, Descricao, Tecnologias, IconeClass
            FROM Projeto
            WHERE UsuarioId = ?
            ORDER BY OrdemExibicao
        """, (usuario_id,))
        projetos = []
        for row in cursor.fetchall():
            projetos.append({
                'Titulo': row.Titulo,
                'Descricao': row.Descricao,
                'Tecnologias': row.Tecnologias,
                'IconeClass': row.IconeClass
            })

    return render_template('projetos.html', projetos=projetos, info={})


@empresa_bp.route('/solicitar-implantacao-directos', methods=['GET', 'POST'])
def solicitar_implantacao_directos():
    utm = {
        'utm_source': _campo_utm('utm_source'),
        'utm_medium': _campo_utm('utm_medium'),
        'utm_campaign': _campo_utm('utm_campaign'),
    }

    if request.method == 'POST':
        form_data = {
            'nome': _campo_formulario('nome'),
            'empresa': _campo_opcional_formulario('empresa'),
            'email': _campo_opcional_formulario('email'),
            'whatsapp': _campo_opcional_formulario('whatsapp'),
            'tipo_negocio': _campo_opcional_formulario('tipo_negocio'),
            'volume_os_mes': _campo_opcional_formulario('volume_os_mes'),
            'mensagem': _campo_opcional_formulario('mensagem'),
        }

        if not form_data['nome']:
            flash('Informe seu nome para solicitar a implantacao assistida.', 'danger')
            return render_template(
                'solicitar_implantacao_directos.html',
                form_data=form_data,
                utm=utm,
            ), 400

        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO APP_LeadsDirectOS
                        (Nome, Empresa, Email, Whatsapp, TipoNegocio, VolumeOSMes,
                         Mensagem, Origem, UtmSource, UtmMedium, UtmCampaign)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        form_data['nome'],
                        form_data['empresa'],
                        form_data['email'],
                        form_data['whatsapp'],
                        form_data['tipo_negocio'],
                        form_data['volume_os_mes'],
                        form_data['mensagem'],
                        'Portal DirectTI - DirectOS',
                        utm['utm_source'],
                        utm['utm_medium'],
                        utm['utm_campaign'],
                    ),
                )

            flash(MENSAGEM_SUCESSO_IMPLANTACAO_DIRECTOS, 'success')
            return redirect(url_for('empresa.solicitar_implantacao_directos'))
        except Exception:
            current_app.logger.exception('Erro ao salvar lead do DirectOS')
            flash(
                'Nao foi possivel enviar a solicitacao agora. Tente novamente em instantes.',
                'danger',
            )
            return render_template(
                'solicitar_implantacao_directos.html',
                form_data=form_data,
                utm=utm,
            ), 500

    return render_template(
        'solicitar_implantacao_directos.html',
        form_data={},
        utm=utm,
    )
    
@empresa_bp.route('/contato', methods=['GET', 'POST'])
def contato():
    servico = request.args.get('servico', '')
    if request.method == 'POST':
        nome = request.form.get('nome')
        email_cliente = request.form.get('email')
        servico = request.form.get('servico') or servico
        mensagem = request.form.get('mensagem')
        
        # Lógica de Envio de E-mail
        mail = current_app.extensions['mail']
        msg = Message(
            subject=f"Novo Contato: {nome} (via Site DIRECTI)",
            recipients=['direct.ti.tec@gmail.com'], # Seu e-mail de destino
            body=f"Nome: {nome}\nE-mail: {email_cliente}\nServiço: {servico or 'Não informado'}\n\nMensagem:\n{mensagem}"
        )
        
        try:
            mail.send(msg)
            flash('Mensagem enviada com sucesso! Entraremos em contato em breve.', 'success')
        except Exception as e:
            print(f"Erro ao enviar: {e}")
            flash('Ocorreu um erro ao enviar a mensagem. Tente novamente mais tarde.', 'danger')
            
        return redirect(url_for('empresa.contato'))
        
    return render_template('contato.html', info={}, servico=servico)

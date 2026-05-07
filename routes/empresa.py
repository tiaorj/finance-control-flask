from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from database import get_db_cursor
from flask_mail import Message

empresa_bp = Blueprint('empresa', __name__)

@empresa_bp.route('/')
def home():
    # A home pode mostrar apenas os 3 primeiros projetos como destaque
    return render_template('empresa.html', info={})

@empresa_bp.route('/projetos')
def projetos():
    with get_db_cursor() as cursor:
        # Busca os projetos da nova tabela conforme sua remodelagem
        cursor.execute("SELECT Titulo, Descricao, Tecnologias, IconeClass FROM Projeto ORDER BY OrdemExibicao")
        projetos = []
        for row in cursor.fetchall():
            projetos.append({
                'Titulo': row.Titulo,
                'Descricao': row.Descricao,
                'Tecnologias': row.Tecnologias,
                'IconeClass': row.IconeClass
            })

    return render_template('projetos.html', projetos=projetos, info={})
    
@empresa_bp.route('/contato', methods=['GET', 'POST'])
def contato():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email_cliente = request.form.get('email')
        mensagem = request.form.get('mensagem')
        
        # Lógica de Envio de E-mail
        mail = current_app.extensions['mail']
        msg = Message(
            subject=f"Novo Contato: {nome} (via Site DIRECTI)",
            recipients=['direct.ti.tec@gmail.com'], # Seu e-mail de destino
            body=f"Nome: {nome}\nE-mail: {email_cliente}\n\nMensagem:\n{mensagem}"
        )
        
        try:
            mail.send(msg)
            flash('Mensagem enviada com sucesso! Entraremos em contato em breve.', 'success')
        except Exception as e:
            print(f"Erro ao enviar: {e}")
            flash('Ocorreu um erro ao enviar a mensagem. Tente novamente mais tarde.', 'danger')
            
        return redirect(url_for('empresa.contato'))
        
    return render_template('contato.html', info={})

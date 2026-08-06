from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf import CSRFProtect
from routes.empresa import empresa_bp
from routes.curriculo import curriculo_bp
from routes.admin import admin_bp, load_user
from routes.main import main_bp
from routes.dashboard import dashboard_bp
from routes.projetos import projetos_bp
from routes.habilidades import habilidades_bp
from routes.certificacoes import certificacoes_bp
from routes.experiencias import experiencias_bp
from dotenv import load_dotenv
from flask import render_template
from routes.formacao import formacao_bp
from config import Config
from routes.financas import financas_bp, financas_legacy_bp
from routes.assinaturas import assinaturas_bp
from routes.metas import metas_bp
from routes.tarefas import tarefas_bp
from routes.veiculos import veiculos_bp
from routes.garantias import garantias_bp
from routes.agenda import agenda_bp
from routes.sistema_admin import sistema_admin_bp
from commands.notificacoes import registrar_comandos
from helpers.admin_auth import usuario_eh_admin
from helpers.modulos import usuario_tem_modulo
from scheduler import configurar_scheduler

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

@app.template_filter('split_techs')
def split_techs(value):
    if not value:
        return []
    return [t.strip() for t in value.split(',')]

app.config.from_object(Config)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.login_view = 'admin.login'
login_manager.login_message = 'Faça login para acessar esta área.'
login_manager.login_message_category = 'warning'
login_manager.init_app(app)
login_manager.user_loader(load_user)

@app.template_filter('formata_data')
def formata_data(value):
    if not value: return "Atual"
    try:
        return value.strftime('%m/%Y')
    except:
        return str(value)[:10]

app.register_blueprint(admin_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(projetos_bp)
app.register_blueprint(habilidades_bp)
app.register_blueprint(certificacoes_bp)
app.register_blueprint(experiencias_bp)
app.register_blueprint(formacao_bp)
app.register_blueprint(financas_bp)
app.register_blueprint(financas_legacy_bp)
app.register_blueprint(assinaturas_bp)
app.register_blueprint(metas_bp)
app.register_blueprint(tarefas_bp)
app.register_blueprint(veiculos_bp)
app.register_blueprint(garantias_bp)
app.register_blueprint(agenda_bp)
app.register_blueprint(sistema_admin_bp)
app.register_blueprint(main_bp)

mail = Mail(app)

app.extensions['mail'] = mail
registrar_comandos(app)
configurar_scheduler(app)

INFO_BASE = {
    'nome': 'DIRECT TI SOLUÇÕES EM TECNOLOGIA LTDA',
    'especialista': 'SEBASTIÃO OLIVEIRA',
    'cargo': 'Analista de Sistemas Sênior & Arquiteto de Software',
    'resumo':'Analista de Sistemas com sólida trajetória e mais de 20 anos de experiência em desenvolvimento Full-stack e arquitetura de sistemas de grande escala. Especialista na sustentação e modernização de ecossistemas legados (ASP Classic) e liderança técnica em projetos críticos. Expertise em performance SQL e Business Intelligence.',
    'contato': {
        'local': 'Rio de Janeiro – RJ',
        'telefone': '(41) 99911-3960',
        'email': 'direct.ti.tec@gmail.com',
        'linkedin': 'linkedin.com/in/sebastião-oliveira-53346833'
    }
}

@app.context_processor
def inject_info():
    return dict(
        INFO_BASE=INFO_BASE,
        usuario_tem_modulo=usuario_tem_modulo,
        usuario_eh_admin=usuario_eh_admin,
    )

app.register_blueprint(empresa_bp)
app.register_blueprint(curriculo_bp)

@app.get('/health')
def health_check():
    return jsonify(status='ok'), 200

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500

@app.template_filter('formato_real')
def formato_real(valor):
    if valor is None:
        return "R$ 0,00"
    v = "{:,.2f}".format(valor)
    return v.replace(',', 'v').replace('.', ',').replace('v', '.')
    
if __name__ == "__main__":
    app.run(debug=app.config.get('DEBUG', False), use_reloader=True)

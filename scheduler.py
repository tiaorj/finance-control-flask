import atexit
import os
from zoneinfo import ZoneInfo


def scheduler_habilitado(app):
    valor = os.getenv('ENABLE_SCHEDULER', app.config.get('ENABLE_SCHEDULER', 'false'))
    return str(valor).strip().lower() == 'true'


def debug_ativo(app):
    flask_debug = os.getenv('FLASK_DEBUG', '').strip().lower()
    return app.debug or flask_debug in {'1', 'true', 'yes'}


def processo_reloader_principal(app):
    if not debug_ativo(app):
        return True
    return os.environ.get('WERKZEUG_RUN_MAIN') == 'true'


def executar_comando_resumo_diario(app):
    with app.app_context():
        comando = app.cli.commands.get('enviar-resumo-diario')
        if not comando:
            app.logger.error("Comando enviar-resumo-diario nao registrado.")
            return

        try:
            comando.callback()
        except Exception:
            app.logger.exception("Erro ao executar envio diario agendado.")


def configurar_scheduler(app):
    if not scheduler_habilitado(app):
        return None

    if not processo_reloader_principal(app):
        app.logger.info("Scheduler ignorado no processo pai do reloader.")
        return None

    if app.extensions.get('scheduler'):
        return app.extensions['scheduler']

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    timezone = ZoneInfo('America/Sao_Paulo')
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        executar_comando_resumo_diario,
        trigger=CronTrigger(hour=8, minute=0, timezone=timezone),
        args=[app],
        id='enviar_resumo_diario',
        name='Enviar resumo diario por e-mail',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )
    scheduler.start()
    app.extensions['scheduler'] = scheduler

    def encerrar_scheduler():
        if scheduler.running:
            scheduler.shutdown(wait=False)

    atexit.register(encerrar_scheduler)
    app.logger.info("Scheduler iniciado com envio diario as 08:00.")
    return scheduler

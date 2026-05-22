from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import click
from flask_mail import Message

from database import get_db_cursor


def normalizar_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str) and valor:
        return datetime.strptime(valor[:10], '%Y-%m-%d').date()
    return valor


def formatar_data(valor):
    data = normalizar_data(valor)
    return data.strftime('%d/%m/%Y') if data else '-'


def formatar_moeda(valor):
    valor = float(valor or 0)
    return f"R$ {valor:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')


def campo(row, nome, default=None):
    try:
        return getattr(row, nome)
    except AttributeError:
        return default


def email_valido(valor):
    valor = (valor or '').strip()
    return valor if '@' in valor else None


def buscar_usuarios(cursor):
    cursor.execute("""
        SELECT UsuarioId, Nome, Username
        FROM Usuarios
        ORDER BY Nome
    """)
    return cursor.fetchall()


def buscar_email_curriculo(cursor, usuario_id):
    try:
        cursor.execute("""
            SELECT TOP 1 Email
            FROM CurriculoPerfil
            WHERE UsuarioId = ?
              AND Email IS NOT NULL
              AND LTRIM(RTRIM(Email)) <> ''
        """, (usuario_id,))
        row = cursor.fetchone()
        return email_valido(row.Email) if row else None
    except Exception:
        return None


def buscar_lancamentos(cursor, usuario_id, inicio, fim):
    cursor.execute("""
        SELECT Descricao, DataVencimento, ValorEstimado
        FROM FIN_Lancamentos
        WHERE UsuarioId = ?
          AND Pago = 0
          AND DataVencimento IS NOT NULL
          AND DataVencimento >= ?
          AND DataVencimento < ?
        ORDER BY DataVencimento ASC, Descricao ASC
    """, (usuario_id, inicio, fim))
    return cursor.fetchall()


def buscar_tarefas(cursor, usuario_id, inicio, fim):
    cursor.execute("""
        SELECT Titulo, ProximaData
        FROM APP_TarefasRecorrentes
        WHERE UsuarioId = ?
          AND Ativa = 1
          AND ProximaData IS NOT NULL
          AND ProximaData >= ?
          AND ProximaData < ?
        ORDER BY ProximaData ASC, Titulo ASC
    """, (usuario_id, inicio, fim))
    return cursor.fetchall()


def buscar_lembretes_veiculos(cursor, usuario_id, inicio, fim):
    cursor.execute("""
        SELECT L.Titulo, L.DataVencimento, V.Apelido
        FROM APP_VeiculoLembretes L
        LEFT JOIN APP_Veiculos V
            ON V.VeiculoId = L.VeiculoId
            AND V.UsuarioId = L.UsuarioId
        WHERE L.UsuarioId = ?
          AND L.Concluido = 0
          AND L.DataVencimento IS NOT NULL
          AND L.DataVencimento >= ?
          AND L.DataVencimento < ?
        ORDER BY L.DataVencimento ASC, L.Titulo ASC
    """, (usuario_id, inicio, fim))
    return cursor.fetchall()


def registrar_log_notificacao(usuario_id, tipo, email_destino, assunto, status, mensagem_erro=None):
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO APP_NotificacaoLogs
                (UsuarioId, Tipo, EmailDestino, Assunto, Status, MensagemErro)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                usuario_id,
                tipo,
                email_destino,
                assunto,
                status,
                str(mensagem_erro)[:4000] if mensagem_erro else None,
            ))
    except Exception as exc:
        click.echo(f"[log-erro] Usuario {usuario_id}: {exc}", err=True)


def montar_corpo(usuario, lancamentos, tarefas, lembretes, hoje, limite):
    nome = campo(usuario, 'Nome', 'Usuario') or 'Usuario'
    linhas = [
        f"Ola, {nome}.",
        "",
        f"Resumo diario de {formatar_data(hoje)} a {formatar_data(limite)}.",
        "",
    ]

    if lancamentos:
        linhas.append("Financeiro:")
        for item in lancamentos:
            descricao = item.Descricao or 'Lancamento pendente'
            linhas.append(
                f"- {formatar_data(item.DataVencimento)} - {descricao} - {formatar_moeda(item.ValorEstimado)}"
            )
        linhas.append("")

    if tarefas:
        linhas.append("Tarefas:")
        for item in tarefas:
            titulo = item.Titulo or 'Tarefa recorrente'
            linhas.append(f"- {formatar_data(item.ProximaData)} - {titulo}")
        linhas.append("")

    if lembretes:
        linhas.append("Veiculos:")
        for item in lembretes:
            titulo = item.Titulo or 'Lembrete de veiculo'
            if item.Apelido:
                titulo = f"{item.Apelido}: {titulo}"
            linhas.append(f"- {formatar_data(item.DataVencimento)} - {titulo}")
        linhas.append("")

    linhas.append("Este e um aviso automatico da DirectTI.")
    return "\n".join(linhas)


def registrar_comandos(app):
    @app.cli.command('enviar-resumo-diario')
    def enviar_resumo_diario():
        """Envia o resumo diario por e-mail para usuarios com pendencias proximas."""
        mail = app.extensions.get('mail')
        if not mail:
            raise click.ClickException("Flask-Mail nao esta configurado em app.extensions['mail'].")

        hoje = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
        limite = hoje + timedelta(days=3)
        fim_exclusivo = limite + timedelta(days=1)

        with get_db_cursor() as cursor:
            usuarios = buscar_usuarios(cursor)

        enviados = 0
        ignorados = 0
        erros = 0

        for usuario in usuarios:
            usuario_id = usuario.UsuarioId
            destinatario = None
            assunto = f"Resumo diario DirectTI - {formatar_data(hoje)}"
            try:
                with get_db_cursor() as cursor:
                    destinatario = (
                        email_valido(campo(usuario, 'Username'))
                        or buscar_email_curriculo(cursor, usuario_id)
                    )
                    if not destinatario:
                        ignorados += 1
                        click.echo(f"[ignorado] Usuario {usuario_id} sem e-mail valido.")
                        continue

                    lancamentos = buscar_lancamentos(cursor, usuario_id, hoje, fim_exclusivo)
                    tarefas = buscar_tarefas(cursor, usuario_id, hoje, fim_exclusivo)
                    lembretes = buscar_lembretes_veiculos(cursor, usuario_id, hoje, fim_exclusivo)

                if not lancamentos and not tarefas and not lembretes:
                    ignorados += 1
                    continue

                corpo = montar_corpo(usuario, lancamentos, tarefas, lembretes, hoje, limite)
                msg = Message(
                    subject=assunto,
                    recipients=[destinatario],
                    body=corpo,
                )
                mail.send(msg)
                registrar_log_notificacao(
                    usuario_id,
                    'resumo_diario',
                    destinatario,
                    assunto,
                    'enviado',
                )
                enviados += 1
                click.echo(f"[enviado] Usuario {usuario_id} -> {destinatario}")
            except Exception as exc:
                registrar_log_notificacao(
                    usuario_id,
                    'resumo_diario',
                    destinatario,
                    assunto,
                    'erro',
                    exc,
                )
                erros += 1
                click.echo(f"[erro] Usuario {usuario_id}: {exc}", err=True)

        click.echo(
            f"Resumo diario finalizado. Enviados: {enviados}. Ignorados: {ignorados}. Erros: {erros}."
        )

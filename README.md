# Controle Financeiro

Aplicação web em Python, Flask e SQL Server para organização de receitas, despesas, categorias, carteiras, metas e períodos financeiros. A área restrita utiliza autenticação de usuários e mantém o banco SQL Server existente.

## Publicação independente

Domínio de produção: `https://financeiro.directti.dev.br`

A aplicação não depende do site institucional para autenticação, rotas ou execução. O entrypoint WSGI é `app:app` e os arquivos públicos ficam em `static/`.

## Variáveis obrigatórias

Configure os valores reais somente no ambiente da plataforma, sem versionar segredos:

- `APP_URL`
- `FLASK_SECRET_KEY`
- `FLASK_ENV=production`
- `FLASK_DEBUG=false`
- `DB_SERVER`
- `DB_DATABASE`
- `DB_USERNAME`
- `DB_PASSWORD`
- `DB_BACKEND` (`pyodbc` quando o driver ODBC estiver disponível)
- `DB_DRIVER`
- `DB_ENCRYPT`
- `DB_TRUST_SERVER_CERTIFICATE`

As variáveis de e-mail são necessárias apenas para os recursos que enviam mensagens. Consulte `.env.example` para placeholders sem segredos.

## Instalação e inicialização

```bash
python -m pip install -r requirements.txt
gunicorn --bind 0.0.0.0:${PORT:-8000} app:app
```

O `Dockerfile` existente usa Gunicorn e aceita a porta fornecida pela plataforma.

## Domínio e proxy HTTPS

Aponte o DNS de `financeiro.directti.dev.br` para a plataforma de hospedagem, habilite TLS e encaminhe `X-Forwarded-For`, `X-Forwarded-Proto` e `X-Forwarded-Host` a partir de um proxy confiável. A aplicação usa `ProxyFix` para reconhecer esses cabeçalhos.

O endpoint `GET /health` retorna `{"status":"ok"}` sem acessar o banco e pode ser usado como health check.

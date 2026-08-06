# Use uma imagem oficial do Python para execucao em producao
FROM python:3.11-slim

# Evita interrupcoes por prompts de configuracao
ENV DEBIAN_FRONTEND=noninteractive

# Instala ferramentas necessarias para o driver SQL Server
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    ca-certificates \
    && apt-get clean

# Baixa a chave da Microsoft e converte para o formato de keyring
RUN curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

# Adiciona o repositorio usando a chave especifica criada acima
RUN echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" > /etc/apt/sources.list.d/mssql-release.list

# Instala o Driver ODBC 17 e dependencias do pyodbc
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y \
    msodbcsql17 \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Configura o diretorio de trabalho
WORKDIR /app

# Instala as dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o codigo-fonte
COPY . .

# Inicia o servidor WSGI para producao usando a porta da plataforma
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} app:app"]

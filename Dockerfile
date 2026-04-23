FROM python:3.12-slim

# Instalar dependencias del sistema necesarias para Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar uv para gestión rápida de paquetes
RUN pip install uv

# Copiar archivos de dependencias
COPY pyproject.toml uv.lock ./

# Instalar dependencias usando uv
RUN uv pip install --system --no-cache -r pyproject.toml

# Instalar navegadores de Playwright (solo Chromium para ahorrar espacio)
RUN playwright install --with-deps chromium

# Copiar el código fuente
COPY navarra_edu_bot/ ./navarra_edu_bot/

# Establecer PYTHONPATH
ENV PYTHONPATH=/app

# Comando por defecto (ejecutar el worker del jueves)
CMD ["python", "-m", "navarra_edu_bot", "run-thursday", "--headless"]

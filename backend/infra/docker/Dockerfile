FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.0 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY requirements/prod.txt requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .

RUN useradd -m -u 1000 tradevision && chown -R tradevision:tradevision /app
USER tradevision

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "60"]

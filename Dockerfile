# Pattika application image (Django + DRF + Celery).
# One image, three roles via CMD: web (gunicorn), celery worker, celery beat.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

# curl: container healthchecks. No compiler needed (psycopg ships binary wheels).
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (cached unless pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project

COPY . .

# Entrypoint must stay executable (COPY can lose the bit via some contexts).
RUN chmod +x /app/entrypoint.sh \
    && uv sync --frozen --no-dev

# Run as non-root; entrypoint needs write access for collectstatic output.
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/staticfiles \
    && chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]

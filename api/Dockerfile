FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    DATABASE_URL=sqlite:////data/epi.db \
    SQLITE_JOURNAL_MODE=DELETE

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY create_admin.py .
COPY entrypoint.sh .

RUN sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh \
    && mkdir -p /data

EXPOSE 8000
VOLUME ["/data"]

ENTRYPOINT ["sh", "/app/entrypoint.sh"]

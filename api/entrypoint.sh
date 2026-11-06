#!/bin/sh
set -e
mkdir -p /data

if [ ! -s /data/epi.db ] && [ -f /seed/epi.db ]; then
  echo "[entrypoint] Copiando banco inicial para /data/epi.db..."
  cp /seed/epi.db /data/epi.db
fi

echo "[entrypoint] Alembic..."
if ! python -m alembic upgrade head; then
  echo "[entrypoint] Alembic upgrade falhou; tentando stamp."
  python -m alembic stamp 0001_admin || echo "[entrypoint] Stamp ignorado."
fi

echo "[entrypoint] init_db..."
python -c "from app.models import init_db; init_db()"

if [ -n "${GOOGLE_CREDENTIALS_JSON:-}" ]; then
  printf '%s' "$GOOGLE_CREDENTIALS_JSON" > /app/app/service_account.json
  export GOOGLE_CREDENTIALS_FILE=/app/app/service_account.json
  echo "[entrypoint] Credencial do Google gravada a partir de GOOGLE_CREDENTIALS_JSON."
fi

if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  echo "[entrypoint] Garantindo usuario admin '${ADMIN_USERNAME}'..."
  python create_admin.py "$ADMIN_USERNAME" "$ADMIN_PASSWORD"
fi

PORT="${PORT:-8000}"
echo "[entrypoint] Uvicorn em 0.0.0.0:${PORT}"
if [ -n "${RAILWAY_ENVIRONMENT:-}" ]; then
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" \
    --proxy-headers --forwarded-allow-ips='*'
fi
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"

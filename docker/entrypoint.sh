#!/usr/bin/env bash
set -euo pipefail

# Wait until PostgreSQL accepts connections before running migrations.
echo "⏳ Esperando a PostgreSQL..."
python - <<'PY'
import asyncio
import sys

import asyncpg

from app.core.config import get_settings

# Single source of truth: reuse the app's assembled DSN (built from POSTGRES_*
# or from DATABASE_URL if set). asyncpg does not understand the "+asyncpg" suffix.
dsn = get_settings().database_url.replace("+asyncpg", "")


async def wait() -> None:
    for attempt in range(30):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            print("✅ PostgreSQL disponible")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"  intento {attempt + 1}/30: {exc}")
            await asyncio.sleep(2)
    print("❌ PostgreSQL no respondió a tiempo", file=sys.stderr)
    sys.exit(1)


asyncio.run(wait())
PY

echo "🛠️  Aplicando migraciones Alembic..."
alembic upgrade head

echo "🚀 Iniciando Anfaia Daily AI..."
exec "$@"

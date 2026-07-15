#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE="$ROOT/.env"

if [[ -z "${DATABASE_URL:-}" && -f "$ENV_FILE" ]]; then
  DATABASE_URL=$(grep -m1 '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2- || true)
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required (environment or $ENV_FILE)." >&2
  exit 1
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$ROOT/sql/schema.sql"
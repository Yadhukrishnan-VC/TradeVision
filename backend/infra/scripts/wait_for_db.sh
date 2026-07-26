#!/usr/bin/env bash
set -e

host="${POSTGRES_HOST:-localhost}"
port="${POSTGRES_PORT:-5432}"
user="${POSTGRES_USER:-tradevision}"
db="${POSTGRES_DB:-tradevision_db}"

echo "Waiting for PostgreSQL at ${host}:${port}..."

until PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "$host" -p "$port" -U "$user" -d "$db" -c '\q' 2>/dev/null; do
  >&2 echo "PostgreSQL is unavailable - sleeping"
  sleep 1
done

>&2 echo "PostgreSQL is up - executing command"
exec "$@"

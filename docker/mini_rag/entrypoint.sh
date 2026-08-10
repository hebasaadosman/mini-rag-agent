#!/bin/sh
set -e

# echo "Running Alembic migrations..."
# cd /app/models/db_schemes/mini_rag

# alembic upgrade head

# cd /app

exec "$@"
#!/bin/bash
set -e

export PATH="/usr/lib/postgresql/18/bin:$PATH"
export DATABASE_URL="postgresql+asyncpg://wirewolf:wirewolf@localhost:5433/wirewolf"

# 确保 PostgreSQL 在运行
if ! pg_isready -h localhost -p 5433 >/dev/null 2>&1; then
    echo "Starting PostgreSQL on port 5433..."
    pg_ctl -D ~/wirewolf_pgdata -l ~/wirewolf_pgdata/postgres.log start
    sleep 2
fi

echo "PostgreSQL ready on localhost:5433"

cd /home/shiyu/wirewolf/backend
echo "Starting WireWolf backend..."
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

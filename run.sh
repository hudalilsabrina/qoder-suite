#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[!] .venv belum ada, menjalankan setup.sh..."
    ./setup.sh
fi

# Deteksi path DB 9router: instance yang jalan bisa pakai DATA_DIR=/var/lib/9router
if [ -z "${NINEROUTER_DB:-}" ]; then
    for p in /var/lib/9router/db/data.sqlite "$HOME/.9router/db/data.sqlite"; do
        if [ -f "$p" ]; then export NINEROUTER_DB="$p"; break; fi
    done
fi

.venv/bin/python main.py "$@"

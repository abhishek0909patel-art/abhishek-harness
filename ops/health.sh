#!/usr/bin/env bash
set -euo pipefail
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8001}
curl -fsS "http://${HOST}:${PORT}/health" || { echo "Health check failed" >&2; exit 1; }

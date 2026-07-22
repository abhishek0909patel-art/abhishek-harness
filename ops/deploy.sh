#!/usr/bin/env bash
set -euo pipefail

TAG=${TAG:-latest}
IMAGE=abhishek-harness/api:${TAG}
COMPOSE_FILE=docker-compose.prod.yml

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Required compose file ${COMPOSE_FILE} not found" >&2
  exit 1
fi

if [[ ! -f .env.production ]]; then
  echo "Missing .env.production — copy .env.example and fill provider values" >&2
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" pull || true
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "Deployment started (${IMAGE}). Tail logs with: docker compose -f ${COMPOSE_FILE} logs -f"

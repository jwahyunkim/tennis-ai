#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly PROJECT_ROOT
cd "${PROJECT_ROOT}"

if [[ ! -f infra/.env ]]; then
    echo "Run bash .devcontainer/scripts/setup-development.sh to create infra/.env first." >&2
    exit 1
fi

docker compose --env-file infra/.env -f infra/compose.yaml config --quiet
docker compose --env-file infra/.env -f infra/compose.yaml up -d --wait --wait-timeout 90 postgres

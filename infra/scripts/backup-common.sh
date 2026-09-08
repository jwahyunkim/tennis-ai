#!/usr/bin/env bash

# Shared checks for the single-host Compose backup and restore commands.
set -euo pipefail

readonly PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly -a COMPOSE=(docker compose --env-file "${PROJECT_ROOT}/infra/.env" -f "${PROJECT_ROOT}/infra/compose.yaml" --profile app)

require_external_directory() {
    local directory
    directory="$(realpath -m -- "$1")"
    if [[ "${directory}" == "${PROJECT_ROOT}" || "${directory}" == "${PROJECT_ROOT}/"* ]]; then
        echo "Keep backups outside the repository." >&2
        return 1
    fi
    printf '%s\n' "${directory}"
}

require_local_storage() {
    "${COMPOSE[@]}" config --quiet
    "${COMPOSE[@]}" run --rm --no-deps -T --entrypoint python api -c '
from backend.core.config import Settings
if Settings().storage_backend != "local":
    raise SystemExit("These scripts support local Compose media only; configure external object-store backups for S3.")
'
}

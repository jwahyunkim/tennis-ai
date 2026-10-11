#!/usr/bin/env bash

set -euo pipefail
umask 077
# shellcheck source=infra/scripts/backup-common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/backup-common.sh"

if [[ $# -ne 1 ]]; then
    echo "Usage: bash infra/scripts/backup.sh /absolute/external/backup-directory" >&2
    exit 2
fi

backup_root="$(require_external_directory "$1")"
require_local_storage
mkdir -p -- "${backup_root}"
backup_directory="$(mktemp -d "${backup_root}/tennis-ai-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
running_containers=()
while IFS= read -r container_id; do
    if [[ -n "${container_id}" ]]; then
        running_containers+=("${container_id}")
    fi
done < <("${COMPOSE[@]}" ps --status running --quiet api worker)

resume_services() {
    if ((${#running_containers[@]})); then
        # Compose start also starts dependencies, including the one-shot migration.
        # Resume the exact original containers without reapplying a migration.
        docker start "${running_containers[@]}" >/dev/null
    fi
}
trap resume_services EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Pause all application writes so database rows and media represent the same point.
"${COMPOSE[@]}" stop api worker
# Expand credentials only inside the container, never in the host process arguments.
# shellcheck disable=SC2016
"${COMPOSE[@]}" exec -T postgres sh -c \
    'pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "${backup_directory}/database.dump"
"${COMPOSE[@]}" run --rm --no-deps -T --entrypoint tar api \
    -C /data/media --exclude=./worker-heartbeat -czf - . > "${backup_directory}/media.tar.gz"
(
    cd "${backup_directory}"
    sha256sum database.dump media.tar.gz > SHA256SUMS
)
printf 'Backup complete: %s\n' "${backup_directory}"

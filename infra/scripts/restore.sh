#!/usr/bin/env bash

set -euo pipefail
umask 077
# shellcheck source=infra/scripts/backup-common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/backup-common.sh"

if [[ $# -ne 2 || "$2" != --confirm-restore ]]; then
    echo "Usage: bash infra/scripts/restore.sh /external/backup-directory --confirm-restore" >&2
    echo "Restore requires an empty PostgreSQL database and an empty Compose media volume." >&2
    exit 2
fi

backup_directory="$(require_external_directory "$1")"
for filename in database.dump media.tar.gz SHA256SUMS; do
    [[ -f "${backup_directory}/${filename}" ]] || { echo "Incomplete backup." >&2; exit 1; }
done
(
    cd "${backup_directory}"
    sha256sum --check --strict SHA256SUMS
)
require_local_storage
"${COMPOSE[@]}" up -d --wait --wait-timeout 90 postgres
"${COMPOSE[@]}" stop api worker

# Query only PostgreSQL's system catalog to prevent overwriting application data.
# This administrative check runs outside the application ORM and accepts no SQL input.
# shellcheck disable=SC2016
table_count="$("${COMPOSE[@]}" exec -T postgres sh -c \
    'psql -X -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT count(*) FROM pg_catalog.pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema');
SQL
)"
if [[ "${table_count}" != 0 ]]; then
    echo "Refusing to replace an existing database. Restore into a fresh Compose project." >&2
    exit 1
fi
"${COMPOSE[@]}" run --rm --no-deps -T --entrypoint python api -c '
from pathlib import Path
if any(Path("/data/media").iterdir()):
    raise SystemExit("Refusing to replace existing media. Use a fresh Compose project.")
'

# Expand credentials inside the container; preserve the single quotes.
# shellcheck disable=SC2016
"${COMPOSE[@]}" exec -T postgres sh -c \
    'pg_restore --exit-on-error --single-transaction --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < "${backup_directory}/database.dump"
"${COMPOSE[@]}" run --rm --no-deps -T --entrypoint python api -c '
import sys
import tarfile
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
    archive.extractall("/data/media", filter="data")
' < "${backup_directory}/media.tar.gz"
echo "Restore complete. API and worker remain stopped; review the restored data, then start the app profile."

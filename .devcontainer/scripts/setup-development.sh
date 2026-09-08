#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=.devcontainer/scripts/dev-env.sh
source "${PROJECT_ROOT}/.devcontainer/scripts/dev-env.sh"
cd "${PROJECT_ROOT}"

python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), "Use Python 3.12 for the checked-in dependency locks"'
flutter pub get --enforce-lockfile
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
backend/.venv/bin/python -m pip check

# Generate a local password only on first setup. Never overwrite existing settings.
backend/.venv/bin/python - <<'PY'
import os
from pathlib import Path
import secrets

env_path = Path("infra/.env")
if not env_path.exists():
    content = Path("infra/.env.example").read_text()
    content = content.replace("POSTGRES_PASSWORD=", f"POSTGRES_PASSWORD={secrets.token_hex(32)}", 1)
    descriptor = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as env_file:
        env_file.write(content)
    print("Created infra/.env with a generated local database password.")
PY

bash .devcontainer/scripts/start-services.sh
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
echo "Development setup complete. Activate Python with: source backend/.venv/bin/activate"

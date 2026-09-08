#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly PROJECT_ROOT
# shellcheck source=.devcontainer/scripts/dev-env.sh
source "${PROJECT_ROOT}/.devcontainer/scripts/dev-env.sh"
cd "${PROJECT_ROOT}"

flutter analyze
flutter test
command -v ffprobe >/dev/null
shellcheck .devcontainer/scripts/*.sh infra/scripts/*.sh
backend/.venv/bin/python -m pip check

# Exercise the backend API, including a real async PostgreSQL readiness check.
backend/.venv/bin/python -m ruff check backend
backend/.venv/bin/python -m ruff format --check backend
RUN_DB_TESTS=1 backend/.venv/bin/python -m pytest -c backend/pyproject.toml
backend/.venv/bin/alembic -c backend/alembic.ini check

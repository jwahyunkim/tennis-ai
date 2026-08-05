#!/usr/bin/env bash

set -euo pipefail
umask 077

readonly PERSISTENT_CODEX_HOME="/workspaces/.codex-persist"
readonly CODEX_HOME_PATH="/home/codespace/.codex"
readonly CODEX_USER="codespace"

fail() {
    echo "Codex persistence setup failed: $*" >&2
    exit 1
}

directory_has_content() {
    [[ -n "$(find "$1" -mindepth 1 -print -quit)" ]]
}

ensure_codespace_access() {
    local foreign_owner

    foreign_owner="$(find "${PERSISTENT_CODEX_HOME}" ! -user "${CODEX_USER}" -print -quit)"
    [[ -z "${foreign_owner}" ]] \
        || fail "${foreign_owner} is not owned by ${CODEX_USER}."

    chmod -R u+rwX,go-rwx "${PERSISTENT_CODEX_HOME}"
    chmod 700 "${PERSISTENT_CODEX_HOME}"
}

link_codex_home() {
    if ! ln -s "${PERSISTENT_CODEX_HOME}" "${CODEX_HOME_PATH}"; then
        return 1
    fi
}

[[ "$(id -un)" == "${CODEX_USER}" ]] \
    || fail "run this script as ${CODEX_USER}."

if [[ -L "${PERSISTENT_CODEX_HOME}" ]]; then
    fail "${PERSISTENT_CODEX_HOME} must be a real directory, not a symbolic link."
elif [[ -e "${PERSISTENT_CODEX_HOME}" && ! -d "${PERSISTENT_CODEX_HOME}" ]]; then
    fail "${PERSISTENT_CODEX_HOME} exists but is not a directory."
fi

mkdir -p "${PERSISTENT_CODEX_HOME}"
ensure_codespace_access

if [[ -L "${CODEX_HOME_PATH}" ]]; then
    persistent_target="$(readlink -f "${PERSISTENT_CODEX_HOME}")"
    current_target="$(readlink -f "${CODEX_HOME_PATH}")" \
        || fail "${CODEX_HOME_PATH} is a broken symbolic link."
    [[ "${current_target}" == "${persistent_target}" ]] \
        || fail "${CODEX_HOME_PATH} points to ${current_target}, not ${persistent_target}."
elif [[ -e "${CODEX_HOME_PATH}" && ! -d "${CODEX_HOME_PATH}" ]]; then
    fail "${CODEX_HOME_PATH} exists but is not a directory."
elif [[ ! -e "${CODEX_HOME_PATH}" ]]; then
    link_codex_home || fail "could not create ${CODEX_HOME_PATH}."
elif ! directory_has_content "${PERSISTENT_CODEX_HOME}"; then
    # Moving the complete home preserves existing login data and config byte-for-byte.
    rmdir "${PERSISTENT_CODEX_HOME}"
    mv "${CODEX_HOME_PATH}" "${PERSISTENT_CODEX_HOME}"
    if ! link_codex_home; then
        mv "${PERSISTENT_CODEX_HOME}" "${CODEX_HOME_PATH}"
        mkdir -m 700 "${PERSISTENT_CODEX_HOME}"
        fail "could not link ${CODEX_HOME_PATH}; the original directory was restored."
    fi
elif ! directory_has_content "${CODEX_HOME_PATH}"; then
    rmdir "${CODEX_HOME_PATH}"
    if ! link_codex_home; then
        mkdir -m 700 "${CODEX_HOME_PATH}"
        fail "could not link ${CODEX_HOME_PATH}; the empty directory was restored."
    fi
else
    # The persistent copy is authoritative. Merge only missing entries so that
    # existing auth.json and config.toml are never overwritten.
    cp -a --no-clobber "${CODEX_HOME_PATH}"/. "${PERSISTENT_CODEX_HOME}"/
    ensure_codespace_access

    # Preserve the complete source directory in case same-name files differed.
    migration_backup="$(mktemp -d /workspaces/.codex-home-before-persistence.XXXXXX)"
    rmdir "${migration_backup}"
    mv "${CODEX_HOME_PATH}" "${migration_backup}"
    chmod -R u+rwX,go-rwx "${migration_backup}"
    chmod 700 "${migration_backup}"

    if ! link_codex_home; then
        mv "${migration_backup}" "${CODEX_HOME_PATH}"
        fail "could not link ${CODEX_HOME_PATH}; the original directory was restored."
    fi

    echo "Original Codex home preserved at ${migration_backup}."
fi

ensure_codespace_access

export PATH="/home/codespace/.local/bin:${PATH}"
codex --version

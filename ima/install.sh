#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="ima"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
TARGET_ROOT="${CODEX_HOME_DIR}/skills"
TARGET_DIR="${TARGET_ROOT}/${SKILL_NAME}"

STAGING_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

mkdir -p "${TARGET_ROOT}"

if [ -e "${TARGET_DIR}" ]; then
  BACKUP_DIR="${TARGET_ROOT}/${SKILL_NAME}.backup.$(date +%Y%m%d%H%M%S)"
  mv "${TARGET_DIR}" "${BACKUP_DIR}"
  printf 'Backed up existing install to %s\n' "${BACKUP_DIR}"
fi

mkdir -p "${STAGING_DIR}/${SKILL_NAME}"
tar \
  --exclude='.venv' \
  --exclude='./.venv' \
  --exclude='data' \
  --exclude='./data' \
  --exclude='__pycache__' \
  --exclude='./__pycache__' \
  --exclude='*/__pycache__' \
  -C "${SCRIPT_DIR}" \
  -cf - \
  . | tar -C "${STAGING_DIR}/${SKILL_NAME}" -xf -

mv "${STAGING_DIR}/${SKILL_NAME}" "${TARGET_DIR}"

printf 'Installed %s to %s\n' "${SKILL_NAME}" "${TARGET_DIR}"
printf 'Next steps:\n'
printf '  1. python3 %s/scripts/run.py auth_manager.py setup\n' "${TARGET_DIR}"
printf '  2. python3 %s/scripts/run.py knowledge_manager.py list --refresh\n' "${TARGET_DIR}"

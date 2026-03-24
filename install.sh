#!/usr/bin/env bash

set -euo pipefail

DEFAULT_REPO="lihuabai629-star/skills"
DEFAULT_REF="main"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
REPO="${DEFAULT_REPO}"
REF="${DEFAULT_REF}"
SOURCE_DIR=""
SKILL_NAMES=()

usage() {
  cat <<'EOF'
Usage:
  install.sh [--repo owner/repo] [--ref git-ref] [--source-dir path] <skill> [<skill> ...]

Examples:
  curl -fsSL https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima
  bash install.sh --source-dir /path/to/skills ima ima-note

Notes:
  - Skills install into ${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>
  - If a skill ships its own install.sh, that installer is used first
EOF
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_value() {
  local flag="$1"
  local value="${2:-}"

  if [ -z "${value}" ]; then
    die "${flag} requires a value"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      require_value "$1" "${2:-}"
      REPO="$2"
      shift 2
      ;;
    --ref)
      require_value "$1" "${2:-}"
      REF="$2"
      shift 2
      ;;
    --source-dir)
      require_value "$1" "${2:-}"
      SOURCE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [ "$#" -gt 0 ]; do
        SKILL_NAMES+=("$1")
        shift
      done
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      SKILL_NAMES+=("$1")
      shift
      ;;
  esac
done

if [ "${#SKILL_NAMES[@]}" -eq 0 ]; then
  usage
  exit 1
fi

STAGING_DIR="$(mktemp -d)"
SOURCE_ROOT=""

cleanup() {
  rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

download_archive() {
  local archive_path="${STAGING_DIR}/skills.tar.gz"
  local archive_url="https://codeload.github.com/${REPO}/tar.gz/${REF}"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "${archive_url}" -o "${archive_path}"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "${archive_path}" "${archive_url}"
  else
    die "curl or wget is required to download skills"
  fi

  local top_level
  top_level="$(tar -tzf "${archive_path}" | head -1)"
  top_level="${top_level%%/*}"

  if [ -z "${top_level}" ]; then
    die "failed to inspect downloaded archive from ${archive_url}"
  fi

  tar -xzf "${archive_path}" -C "${STAGING_DIR}"
  SOURCE_ROOT="${STAGING_DIR}/${top_level}"
}

prepare_source_root() {
  if [ -n "${SOURCE_DIR}" ]; then
    if [ ! -d "${SOURCE_DIR}" ]; then
      die "source directory does not exist: ${SOURCE_DIR}"
    fi
    SOURCE_ROOT="$(cd "${SOURCE_DIR}" && pwd)"
    return
  fi

  download_archive
}

validate_skill_dir() {
  local skill_name="$1"
  local skill_dir="${SOURCE_ROOT}/${skill_name}"

  if [ ! -d "${skill_dir}" ] || [ ! -f "${skill_dir}/SKILL.md" ]; then
    die "skill '${skill_name}' not found in ${SOURCE_ROOT}"
  fi
}

generic_install() {
  local skill_name="$1"
  local skill_dir="${SOURCE_ROOT}/${skill_name}"
  local target_root="${CODEX_HOME_DIR}/skills"
  local target_dir="${target_root}/${skill_name}"

  mkdir -p "${target_root}"

  if [ -e "${target_dir}" ]; then
    local backup_dir="${target_root}/${skill_name}.backup.$(date +%Y%m%d%H%M%S)"
    mv "${target_dir}" "${backup_dir}"
    log "Backed up existing install to ${backup_dir}"
  fi

  mkdir -p "${STAGING_DIR}/install"
  local install_dir="${STAGING_DIR}/install/${skill_name}"
  mkdir -p "${install_dir}"

  tar \
    --exclude='.venv' \
    --exclude='./.venv' \
    --exclude='__pycache__' \
    --exclude='./__pycache__' \
    --exclude='*/__pycache__' \
    -C "${skill_dir}" \
    -cf - \
    . | tar -C "${install_dir}" -xf -

  mv "${install_dir}" "${target_dir}"
  log "Installed ${skill_name} to ${target_dir}"
}

install_skill() {
  local skill_name="$1"
  local skill_dir="${SOURCE_ROOT}/${skill_name}"
  local install_script="${skill_dir}/install.sh"

  validate_skill_dir "${skill_name}"

  if [ -f "${install_script}" ]; then
    CODEX_HOME="${CODEX_HOME_DIR}" bash "${install_script}"
    return
  fi

  generic_install "${skill_name}"
}

prepare_source_root

for skill_name in "${SKILL_NAMES[@]}"; do
  install_skill "${skill_name}"
done

log "Restart Codex to pick up new skills."

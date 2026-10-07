#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/lib/common.sh"
init_paths

usage() {
  cat <<'EOF'
Usage:
  sudo bash deploy/install-online.sh [--user USER] [--no-start] [--skip-firewall] [--dry-run]
  sudo bash deploy/install-online.sh --prepare-offline OUTPUT_DIR [--user USER] [--dry-run]

Install/update PipeSight online, or prepare a complete offline distribution.
Default service account: robot (must already exist); override with --user USER.
OUTPUT_DIR must not already exist. Preparation does not install PipeSight services.
Targets: Ubuntu 22.04 amd64/arm64; prepare on the same OS and architecture as the target.
EOF
}

PREPARE_DIR=''
while (( $# )); do
  case "$1" in
    --user|--prepare-offline)
      if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then die "Missing value for $1"; fi
      if [[ "$1" == --user ]]; then RUN_USER="$2"; else PREPARE_DIR="$2"; fi
      shift 2 ;;
    --no-start) NO_START=1; shift ;;
    --skip-firewall) SKIP_FIREWALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (use --help)" ;;
  esac
done
preflight
if (( DRY_RUN )); then
  printf 'Mode: online\nProject: %s\nUser: %s\nPlatform: Ubuntu 22.04 %s\nNode: %s\nMediaMTX: %s\n' \
    "$REPO_DIR" "$RUN_USER" "$ARCH" "$NODE_VERSION" "$MEDIAMTX_VERSION"
  printf 'Offline output: %s\nSystem packages: %s\n' "${PREPARE_DIR:-none (install services)}" "${SYSTEM_PACKAGES[*]}"
  exit 0
fi
if [[ -n "$PREPARE_DIR" ]]; then prepare_offline "$PREPARE_DIR"; else install_project online; fi

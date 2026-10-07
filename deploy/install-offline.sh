#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/lib/common.sh"
init_paths
BUNDLE_DIR="$DEPLOY_DIR/offline"

usage() {
  cat <<'EOF'
Usage:
  sudo bash deploy/install-offline.sh [--bundle DIR] [--user USER] [--no-start] [--skip-firewall] [--dry-run]

Install/update using a verified local bundle only (no network repositories).
Default bundle: deploy/offline inside the extracted offline distribution.
Prepare first: sudo bash deploy/install-online.sh --prepare-offline OUTPUT_DIR
EOF
}

while (( $# )); do
  case "$1" in
    --user|--bundle)
      if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then die "Missing value for $1"; fi
      if [[ "$1" == --user ]]; then RUN_USER="$2"; else BUNDLE_DIR="$2"; fi
      shift 2 ;;
    --no-start) NO_START=1; shift ;;
    --skip-firewall) SKIP_FIREWALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (use --help)" ;;
  esac
done
preflight
BUNDLE_DIR="$(realpath -m -- "$BUNDLE_DIR")"
check_bundle "$BUNDLE_DIR"
if (( DRY_RUN )); then
  printf 'Mode: offline\nProject: %s\nBundle: %s\nPlatform: Ubuntu 22.04 %s\n' "$REPO_DIR" "$BUNDLE_DIR" "$ARCH"
  # Validate source/interpreter compatibility when Python is already present.
  if [[ -x "$PYTHON" ]]; then "$PYTHON" "$HELPER" validate "$REPO_DIR" "$BUNDLE_DIR"; fi
  exit 0
fi
install_project offline "$BUNDLE_DIR"

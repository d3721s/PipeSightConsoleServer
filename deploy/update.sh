#!/usr/bin/env bash
#
# PipeSight offline-friendly update script.
#
# By default this script does not use the network:
#   - front-end: npm run build only, using existing node_modules
#   - backend:   use existing server/.venv only, no pip install
#   - bridge:    rebuild the local C++ bridge
#   - services:  restart systemd units
#
# Use --pip or --npm-install explicitly only on a machine that can reach package
# indexes, or one that has pip/npm configured to use a local mirror/cache.
#
# Usage:
#   sudo bash deploy/update.sh
#   sudo bash deploy/update.sh --back --bridge
#   sudo bash deploy/update.sh --front
#   sudo bash deploy/update.sh --service
#   sudo bash deploy/update.sh --back --pip
#   sudo bash deploy/update.sh --front --npm-install
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_DIR="$(dirname "$DEPLOY_DIR")"
SERVER_DIR="$REPO_DIR/server"
FRONT_DIR="$REPO_DIR/front_end"
BRIDGE_DIR="$REPO_DIR/pointcloud_bridge"
SDK_LIB_DIR="$REPO_DIR/3d_camera/linux/libs/lib/x86_64-linux-gnu"

RUN_USER="${SUDO_USER:-$USER}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo: sudo bash deploy/update.sh" >&2
  exit 1
fi

run_as_user() { sudo -u "$RUN_USER" "$@"; }

DO_FRONT=0
DO_BACK=0
DO_BRIDGE=0
SELECTED=0
NO_BRIDGE=0
DO_SERVICE=0
DO_PIP=0
DO_NPM_INSTALL=0

usage() {
  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --front) DO_FRONT=1; SELECTED=1 ;;
    --back) DO_BACK=1; SELECTED=1 ;;
    --bridge) DO_BRIDGE=1; SELECTED=1 ;;
    --no-bridge) NO_BRIDGE=1 ;;
    --service) DO_SERVICE=1 ;;
    --pip|--deps) DO_PIP=1 ;;
    --no-pip|--skip-pip|--offline) DO_PIP=0; DO_NPM_INSTALL=0 ;;
    --npm-install) DO_NPM_INSTALL=1 ;;
    --no-npm-install) DO_NPM_INSTALL=0 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ "$SELECTED" -eq 0 ]; then
  DO_FRONT=1
  DO_BACK=1
  DO_BRIDGE=1
fi
[ "$NO_BRIDGE" -eq 1 ] && DO_BRIDGE=0

echo "==> Repo: $REPO_DIR"
echo "==> User: $RUN_USER"
echo "==> Plan: front=$DO_FRONT back=$DO_BACK bridge=$DO_BRIDGE service=$DO_SERVICE pip=$DO_PIP npm_install=$DO_NPM_INSTALL"

# --- front-end build -------------------------------------------------------
if [ "$DO_FRONT" -eq 1 ]; then
  echo "==> Building front-end..."
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm not found. Install Node.js/npm, or skip front-end with --back/--bridge." >&2
    exit 1
  fi
  if [ "$DO_NPM_INSTALL" -eq 1 ]; then
    run_as_user bash -lc "cd '$FRONT_DIR' && npm install && npm run build"
  else
    if [ ! -d "$FRONT_DIR/node_modules" ]; then
      echo "ERROR: $FRONT_DIR/node_modules not found." >&2
      echo "       Offline mode will not run npm install. Copy node_modules, or rerun with --npm-install on a networked machine." >&2
      exit 1
    fi
    run_as_user bash -lc "cd '$FRONT_DIR' && npm run build"
  fi
fi

# --- backend venv ----------------------------------------------------------
if [ "$DO_BACK" -eq 1 ]; then
  VENV_PY="$SERVER_DIR/.venv/bin/python"
  echo "==> Checking backend venv..."
  if [ ! -x "$VENV_PY" ]; then
    if [ -d "$SERVER_DIR/.venv/Scripts" ]; then
      echo "ERROR: $SERVER_DIR/.venv looks like a Windows venv (Scripts/ found)." >&2
      echo "       Copy an Ubuntu/Linux venv that contains .venv/bin/python." >&2
    else
      echo "ERROR: $SERVER_DIR/.venv/bin/python not found." >&2
      echo "       Copy your Ubuntu venv to server/.venv or create it on this machine." >&2
    fi
    exit 1
  fi

  run_as_user env PYTHONPATH="$SERVER_DIR" "$VENV_PY" -c '
import importlib
import sys

modules = [
    "fastapi",
    "uvicorn",
    "pydantic_settings",
    "sqlalchemy",
    "httpx",
    "multipart",
    "reportlab",
    "pymodbus",
    "serial",
    "websockets",
]

missing = []
for module in modules:
    try:
        importlib.import_module(module)
    except Exception as exc:
        missing.append(f"{module}: {exc}")

if missing:
    print("ERROR: existing .venv is missing required backend packages:", file=sys.stderr)
    for item in missing:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)

print("Existing .venv dependency check OK")
'

  if [ "$DO_PIP" -eq 1 ]; then
    echo "==> Updating backend deps with pip..."
    run_as_user bash -lc "cd '$SERVER_DIR' && .venv/bin/python -m pip install --no-build-isolation -e ."
  else
    echo "==> Skipping pip install; using existing .venv."
  fi

  if [ ! -f "$SERVER_DIR/.env" ] && [ -f "$SERVER_DIR/.env.example" ]; then
    run_as_user cp "$SERVER_DIR/.env.example" "$SERVER_DIR/.env"
  fi
fi

# --- C++ point-cloud bridge ------------------------------------------------
if [ "$DO_BRIDGE" -eq 1 ]; then
  if [ -d "$BRIDGE_DIR" ] && [ -f "$BRIDGE_DIR/build.sh" ]; then
    echo "==> Building point-cloud bridge..."
    run_as_user bash -lc "cd '$BRIDGE_DIR' && bash build.sh" || {
      echo "WARN: bridge build failed; 3D point cloud will be unavailable until fixed." >&2
    }
  else
    echo "WARN: $BRIDGE_DIR not found; skipping bridge." >&2
  fi
fi

# --- optional systemd unit refresh -----------------------------------------
install_unit() {
  local src="$1" dst="/etc/systemd/system/$2"
  sed \
    -e "s|__USER__|$RUN_USER|g" \
    -e "s|__SERVER_DIR__|$SERVER_DIR|g" \
    -e "s|__BRIDGE_DIR__|$BRIDGE_DIR|g" \
    -e "s|__SDK_LIB_DIR__|$SDK_LIB_DIR|g" \
    "$src" > "$dst"
  echo "   installed $dst"
}

if [ "$DO_SERVICE" -eq 1 ]; then
  echo "==> Re-installing systemd unit files..."
  install_unit "$DEPLOY_DIR/pipesight-backend.service" "pipesight-backend.service"
  if [ -x "$BRIDGE_DIR/pointcloud_bridge" ]; then
    install_unit "$DEPLOY_DIR/pipesight-pcl-bridge.service" "pipesight-pcl-bridge.service"
  fi
  systemctl daemon-reload
fi

# --- restart services ------------------------------------------------------
echo "==> Restarting services..."
restart_if_present() {
  local unit="$1"
  if systemctl cat "$unit" >/dev/null 2>&1; then
    systemctl restart "$unit" && echo "   restarted $unit"
  else
    echo "   skip $unit (not installed; run install.sh or update.sh --service first)"
  fi
}

if [ "$DO_FRONT" -eq 1 ] || [ "$DO_BACK" -eq 1 ]; then
  restart_if_present pipesight-backend.service
fi
if [ "$DO_BRIDGE" -eq 1 ]; then
  restart_if_present pipesight-pcl-bridge.service
fi

echo ""
echo "==> Update done. Status:"
systemctl --no-pager --lines=0 status pipesight-backend.service || true
[ "$DO_BRIDGE" -eq 1 ] && systemctl --no-pager --lines=0 status pipesight-pcl-bridge.service || true
echo ""
echo "Open:        http://<this-machine-ip>:8000"
echo "Backend log: journalctl -u pipesight-backend -f"
echo "Bridge log:  journalctl -u pipesight-pcl-bridge -f"

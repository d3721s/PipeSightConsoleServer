#!/usr/bin/env bash
#
# PipeSight fast update — rebuild + restart after pulling new code.
#
# Unlike deploy/install.sh (the full first-time setup), this script assumes the
# machine is already provisioned: system packages, Node, MediaMTX, udev rules,
# user groups, firewall and the systemd unit files are all in place. It only
# redoes the parts that change with the code, then restarts the services.
#
#   - front-end: npm install (incremental) + npm run build
#   - backend:   pip install -e .  (incremental; near-instant if deps unchanged)
#   - bridge:    re-compile the C++ point-cloud bridge
#   - restart the backend (and bridge) systemd services
#
# Usage:
#   cd ~/PipeSightConsoleServer
#   sudo bash deploy/update.sh                 # rebuild everything + restart
#
#   # Build only part of it (skip the rest) — handy when you touched one area:
#   sudo bash deploy/update.sh --front         # front-end only
#   sudo bash deploy/update.sh --back          # backend only
#   sudo bash deploy/update.sh --bridge        # C++ bridge only
#   sudo bash deploy/update.sh --back --front  # combine flags as needed
#
#   sudo bash deploy/update.sh --no-bridge     # everything EXCEPT the bridge
#                                              # (the bridge compile is the slow
#                                              #  part; skip it for FE/BE-only changes)
#   sudo bash deploy/update.sh --service       # also re-install the systemd unit
#                                              # files (only needed if you edited
#                                              # deploy/*.service)
#
# If install.sh has never been run on this machine, run that first instead.
set -euo pipefail

# --- resolve paths / user (same layout as install.sh) ----------------------
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

# --- parse flags -----------------------------------------------------------
# With no part-selecting flag, do front + back + bridge. Any explicit --front/
# --back/--bridge switches to "only what you asked". --no-bridge / --service are
# modifiers on top of that.
DO_FRONT=0; DO_BACK=0; DO_BRIDGE=0; SELECTED=0
NO_BRIDGE=0; DO_SERVICE=0

for arg in "$@"; do
  case "$arg" in
    --front)     DO_FRONT=1; SELECTED=1 ;;
    --back)      DO_BACK=1;  SELECTED=1 ;;
    --bridge)    DO_BRIDGE=1; SELECTED=1 ;;
    --no-bridge) NO_BRIDGE=1 ;;
    --service)   DO_SERVICE=1 ;;
    -h|--help)
      sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 1 ;;
  esac
done

if [ "$SELECTED" -eq 0 ]; then
  DO_FRONT=1; DO_BACK=1; DO_BRIDGE=1
fi
[ "$NO_BRIDGE" -eq 1 ] && DO_BRIDGE=0

echo "==> Repo: $REPO_DIR"
echo "==> User: $RUN_USER"
echo "==> Plan: front=$DO_FRONT back=$DO_BACK bridge=$DO_BRIDGE service=$DO_SERVICE"

# --- front-end build -------------------------------------------------------
if [ "$DO_FRONT" -eq 1 ]; then
  echo "==> Building front-end..."
  run_as_user bash -lc "cd '$FRONT_DIR' && npm install && npm run build"
fi

# --- backend deps ----------------------------------------------------------
if [ "$DO_BACK" -eq 1 ]; then
  echo "==> Updating backend deps..."
  if [ ! -f "$SERVER_DIR/.venv/bin/activate" ]; then
    echo "ERROR: $SERVER_DIR/.venv not found — run deploy/install.sh first." >&2
    exit 1
  fi
  run_as_user bash -lc "cd '$SERVER_DIR' && .venv/bin/python -m pip install -e ."
fi

# --- C++ point-cloud bridge ------------------------------------------------
if [ "$DO_BRIDGE" -eq 1 ]; then
  if [ -d "$BRIDGE_DIR" ] && [ -f "$BRIDGE_DIR/build.sh" ]; then
    echo "==> Building point-cloud bridge..."
    run_as_user bash -lc "cd '$BRIDGE_DIR' && bash build.sh" || {
      echo "WARN: bridge build failed — 3D point cloud will be unavailable until fixed." >&2
    }
  else
    echo "WARN: $BRIDGE_DIR not found; skipping bridge." >&2
  fi
fi

# --- (optional) refresh systemd unit files ---------------------------------
if [ "$DO_SERVICE" -eq 1 ]; then
  echo "==> Re-installing systemd unit files..."
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
  install_unit "$DEPLOY_DIR/pipesight-backend.service" "pipesight-backend.service"
  [ -x "$BRIDGE_DIR/pointcloud_bridge" ] &&
    install_unit "$DEPLOY_DIR/pipesight-pcl-bridge.service" "pipesight-pcl-bridge.service"
  systemctl daemon-reload
fi

# --- restart services ------------------------------------------------------
# Restart the backend whenever code that it serves changed (front-end build is
# served by the backend, and backend deps obviously affect it). Restart the
# bridge only when it was rebuilt.
echo "==> Restarting services..."
restart_if_present() {
  local unit="$1"
  if systemctl list-unit-files "$unit" >/dev/null 2>&1 &&
     systemctl cat "$unit" >/dev/null 2>&1; then
    systemctl restart "$unit" && echo "   restarted $unit"
  else
    echo "   skip $unit (not installed — run install.sh first)"
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

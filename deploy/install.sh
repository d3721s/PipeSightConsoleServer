#!/usr/bin/env bash
#
# PipeSight one-shot deploy + autostart installer for Ubuntu 22.04.
#
# Sets up everything needed to run on boot via systemd:
#   - system packages (ffmpeg, fonts, python venv, build tools)
#   - Python backend venv + deps
#   - front-end production build (served by the backend at :8000)
#   - the C++ point-cloud bridge (built against the bundled Angstrong SDK)
#   - two systemd services (backend + bridge), enabled to start on boot
#
# Usage:
#   cd ~/PipeSightConsoleServer
#   sudo bash deploy/install.sh
#
# Re-run it any time after pulling new code to rebuild + restart everything.
set -euo pipefail

# --- resolve paths / user --------------------------------------------------
# Repo root = parent of this deploy/ dir.
DEPLOY_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_DIR="$(dirname "$DEPLOY_DIR")"
SERVER_DIR="$REPO_DIR/server"
FRONT_DIR="$REPO_DIR/front_end"
BRIDGE_DIR="$REPO_DIR/pointcloud_bridge"
SDK_LIB_DIR="$REPO_DIR/3d_camera/linux/libs/lib/x86_64-linux-gnu"

# The non-root user who owns the files (so services don't run as root and the
# venv/build artifacts stay owned by the user). Works under sudo.
RUN_USER="${SUDO_USER:-$USER}"

echo "==> Repo:    $REPO_DIR"
echo "==> User:    $RUN_USER"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo: sudo bash deploy/install.sh" >&2
  exit 1
fi

run_as_user() { sudo -u "$RUN_USER" "$@"; }

# --- 1. system packages ----------------------------------------------------
echo "==> Installing system packages..."
apt-get update -y
apt-get install -y \
  python3 python3-venv python3-pip \
  ffmpeg fonts-wqy-zenhei fonts-noto-cjk \
  build-essential g++ \
  nodejs npm \
  curl

# Serial access for the chassis + IMU.
usermod -aG dialout "$RUN_USER" || true

# --- 1b. MediaMTX binary (not in apt; the backend auto-launches it) ---------
MEDIAMTX_FALLBACK_VERSION="v1.15.2"
install_mediamtx() {
  if command -v mediamtx >/dev/null 2>&1; then
    echo "==> MediaMTX already installed: $(command -v mediamtx)"
    return 0
  fi
  if [ -x "$SERVER_DIR/third_party/mediamtx/mediamtx" ]; then
    echo "==> MediaMTX present in third_party; skipping download."
    return 0
  fi

  local arch asset ver url tmp
  case "$(uname -m)" in
    x86_64)  arch="amd64" ;;
    aarch64) arch="arm64" ;;
    armv7l)  arch="armv7" ;;
    *) echo "WARN: unknown arch $(uname -m); install MediaMTX manually." >&2; return 1 ;;
  esac

  # Latest tag from GitHub, fall back to a known-good version if the API fails.
  ver="$(curl -fsSL https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
        | grep -oP '"tag_name"\s*:\s*"\K[^"]+' || true)"
  [ -n "$ver" ] || ver="$MEDIAMTX_FALLBACK_VERSION"

  asset="mediamtx_${ver}_linux_${arch}.tar.gz"
  url="https://gh-proxy.org/https://github.com/bluenviron/mediamtx/releases/download/${ver}/${asset}"
  echo "==> Downloading MediaMTX ${ver} (${arch})..."
  tmp="$(mktemp -d)"
  if curl -fsSL "$url" -o "$tmp/mtx.tar.gz"; then
    tar -xzf "$tmp/mtx.tar.gz" -C "$tmp"
    install -m 755 "$tmp/mediamtx" /usr/local/bin/mediamtx
    rm -rf "$tmp"
    echo "==> Installed: $(/usr/local/bin/mediamtx --version 2>/dev/null || echo /usr/local/bin/mediamtx)"
  else
    rm -rf "$tmp"
    echo "WARN: MediaMTX download failed ($url). Camera preview/recording will" >&2
    echo "      not work until you install it manually. See deploy/README.md." >&2
    return 1
  fi
}
install_mediamtx || true

# --- 2. front-end production build -----------------------------------------
echo "==> Building front-end..."
run_as_user bash -lc "cd '$FRONT_DIR' && npm install && npm run build"

# --- 3. backend venv + deps ------------------------------------------------
echo "==> Setting up backend venv..."
run_as_user bash -lc "
  cd '$SERVER_DIR'
  if [ ! -f .venv/bin/activate ]; then python3 -m venv .venv; fi
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e .
"
# Seed .env from the example if absent (so EnvironmentFile has something).
if [ ! -f "$SERVER_DIR/.env" ] && [ -f "$SERVER_DIR/.env.example" ]; then
  run_as_user cp "$SERVER_DIR/.env.example" "$SERVER_DIR/.env"
fi

# --- 4. C++ point-cloud bridge ---------------------------------------------
if [ -d "$BRIDGE_DIR" ] && [ -f "$BRIDGE_DIR/build.sh" ]; then
  echo "==> Building point-cloud bridge..."
  run_as_user bash -lc "cd '$BRIDGE_DIR' && bash build.sh" || {
    echo "WARN: bridge build failed — 3D point cloud will be unavailable until fixed." >&2
  }
else
  echo "WARN: $BRIDGE_DIR not found; skipping bridge." >&2
fi

# --- 5. install systemd services -------------------------------------------
echo "==> Installing systemd services..."
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

ENABLE_BRIDGE=0
if [ -x "$BRIDGE_DIR/pointcloud_bridge" ]; then
  install_unit "$DEPLOY_DIR/pipesight-pcl-bridge.service" "pipesight-pcl-bridge.service"
  ENABLE_BRIDGE=1
fi

systemctl daemon-reload
systemctl enable --now pipesight-backend.service
if [ "$ENABLE_BRIDGE" -eq 1 ]; then
  systemctl enable --now pipesight-pcl-bridge.service
fi

# --- 6. firewall (only if ufw is active) -----------------------------------
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo "==> Opening firewall ports (ufw is active)..."
  ufw allow 8000/tcp  >/dev/null 2>&1 || true   # Web UI / API
  ufw allow 8889/tcp  >/dev/null 2>&1 || true   # WebRTC signaling (WHEP)
  ufw allow 8189/udp  >/dev/null 2>&1 || true   # WebRTC media (required!)
  ufw allow 8554/tcp  >/dev/null 2>&1 || true   # MediaMTX RTSP
  ufw allow 9090/tcp  >/dev/null 2>&1 || true   # point-cloud WebSocket
  echo "   opened 8000, 8889, 8554/tcp, 8189/udp, 9090/tcp"
fi

echo ""
echo "==> Done. Services:"
systemctl --no-pager --lines=0 status pipesight-backend.service || true
[ "$ENABLE_BRIDGE" -eq 1 ] && systemctl --no-pager --lines=0 status pipesight-pcl-bridge.service || true
echo ""
echo "Open:        http://<this-machine-ip>:8000"
echo "Backend log: journalctl -u pipesight-backend -f"
echo "Bridge log:  journalctl -u pipesight-pcl-bridge -f"
echo "NOTE: the dialout group was added — if serial (chassis/IMU) fails, reboot once."

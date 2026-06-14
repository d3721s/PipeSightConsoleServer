#!/usr/bin/env bash
#
# Remove PipeSight systemd services (does NOT touch code, venv, or storage).
#   sudo bash deploy/uninstall.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo: sudo bash deploy/uninstall.sh" >&2
  exit 1
fi

for svc in pipesight-backend pipesight-pcl-bridge; do
  systemctl disable --now "$svc.service" 2>/dev/null || true
  rm -f "/etc/systemd/system/$svc.service"
done
systemctl daemon-reload
echo "Removed PipeSight services. Code/venv/storage left intact."

#!/usr/bin/env bash
# Shared implementation. Only install-online.sh / install-offline.sh are entrypoints.

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
run_as_user() { runuser -u "$RUN_USER" -- "$@"; }

init_paths() {
  DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
  REPO_DIR="$(cd -- "$DEPLOY_DIR/.." && pwd -P)"
  SERVER_DIR="$REPO_DIR/server"
  FRONT_DIR="$REPO_DIR/front_end"
  BRIDGE_DIR="$REPO_DIR/pointcloud_bridge"
  RUNTIME_DIR="$REPO_DIR/.deploy"
  HELPER="$DEPLOY_DIR/lib/bundle.py"
  PYTHON=/usr/bin/python3
  RUN_USER="${RUN_USER:-robot}"
  NO_START=0
  SKIP_FIREWALL=0
  DRY_RUN=0
  WORK_DIR=""
  # shellcheck source=../config/versions.env
  source "$DEPLOY_DIR/config/versions.env"
  mapfile -t SYSTEM_PACKAGES < <(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$DEPLOY_DIR/config/system-packages.txt")
}

preflight() {
  [[ "$(uname -s)" == Linux ]] || die 'Run this installer on Ubuntu 22.04 Linux.'
  # shellcheck source=/dev/null
  source /etc/os-release
  [[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || die "Expected Ubuntu 22.04; found $ID $VERSION_ID."
  ARCH="$(dpkg --print-architecture)"
  case "$ARCH" in
    amd64) NODE_ARCH=x64; SDK_ARCH=x86_64-linux-gnu ;;
    arm64) NODE_ARCH=arm64; SDK_ARCH=aarch64-linux-gnu ;;
    *) die "Unsupported architecture: $ARCH (supported: amd64, arm64)." ;;
  esac
  SDK_LIB_DIR="$REPO_DIR/3d_camera/linux/libs/lib/$SDK_ARCH"
  if [[ -n "${PIPESIGHT_DEPLOY_RUNTIME_DIR:-}" ]]; then
    RUNTIME_DIR="$(realpath -m -- "$PIPESIGHT_DEPLOY_RUNTIME_DIR")"
  fi
  NODE_ASSET="node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"
  MTX_ASSET="mediamtx_${MEDIAMTX_VERSION}_linux_${ARCH}.tar.gz"
  [[ -f "$SERVER_DIR/pyproject.toml" && -f "$FRONT_DIR/package-lock.json" ]] || die 'Incomplete project checkout.'
  [[ -f "$SDK_LIB_DIR/libAngstrongCameraSdk.so" ]] || die "Missing bundled camera SDK: $SDK_LIB_DIR"
  [[ "$REPO_DIR" != *'$'* && "$REPO_DIR" != *$'\n'* ]] || die 'Project path must not contain dollar signs or newlines.'
  if (( ! DRY_RUN )); then
    [[ $EUID -eq 0 ]] || die 'Run with sudo (or as root with --user USER).'
    [[ "$RUN_USER" != root ]] || die 'Specify a non-root service account with --user USER.'
    id "$RUN_USER" >/dev/null 2>&1 || die "Service account does not exist: $RUN_USER"
    RUN_GROUP="$(id -gn "$RUN_USER")"
    command -v flock >/dev/null || die 'flock is required (Ubuntu util-linux).'
    exec 200>/run/lock/pipesight-install.lock
    flock -n 200 || die 'Another PipeSight installation is running.'
  fi
}

require_systemd() {
  [[ -d /run/systemd/system ]] || die 'A running systemd is required for installation; --prepare-offline only prepares files.'
}

cleanup() {
  # Only remove the private directory created by this process.
  if [[ -n "$WORK_DIR" && "$WORK_DIR" == /var/tmp/pipesight-deploy.* && -d "$WORK_DIR" ]]; then
    rm -rf -- "$WORK_DIR"
  fi
}

make_workdir() {
  WORK_DIR="$(mktemp -d /var/tmp/pipesight-deploy.XXXXXX)"
  chown "$RUN_USER:$RUN_GROUP" "$WORK_DIR"
  trap cleanup EXIT
  trap 'printf "ERROR: installation failed at line %s; see the preceding error.\n" "$LINENO" >&2' ERR
}

install_system_online() {
  log 'Installing Ubuntu runtime and build dependencies'
  apt-get -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::Retries=2 update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --no-remove "${SYSTEM_PACKAGES[@]}"
}

download() {
  curl --fail --location --retry 3 --connect-timeout 15 --max-time 600 --silent --show-error "$1" --output "$2"
}

verify_download() {
  local directory="$1" sums="$2" asset="$3"
  local entry
  entry="$(awk -v name="$asset" '$2 == name || $2 == "*"name {print}' "$sums")"
  [[ -n "$entry" ]] || die "Upstream checksum missing for $asset"
  (cd -- "$directory" && printf '%s\n' "$entry" | sha256sum --check --strict)
}

fetch_tools() {
  local destination="$1"
  mkdir -p "$destination/node" "$destination/mediamtx"
  log "Downloading Node.js $NODE_VERSION and MediaMTX $MEDIAMTX_VERSION"
  download "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ASSET}" "$destination/node/$NODE_ASSET"
  download "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" "$destination/node/SHASUMS256.txt"
  verify_download "$destination/node" "$destination/node/SHASUMS256.txt" "$NODE_ASSET"
  download "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/${MTX_ASSET}" "$destination/mediamtx/$MTX_ASSET"
  download "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/checksums.sha256" "$destination/mediamtx/checksums.sha256"
  verify_download "$destination/mediamtx" "$destination/mediamtx/checksums.sha256" "$MTX_ASSET"
}

extract_tools() {
  local cache="$1" output="$2"
  mkdir -p "$output/node" "$output/mediamtx"
  tar -xJf "$cache/node/$NODE_ASSET" -C "$output/node" --strip-components=1
  tar -xzf "$cache/mediamtx/$MTX_ASSET" -C "$output/mediamtx" mediamtx
  chown -R "$RUN_USER:$RUN_GROUP" "$output/node" "$output/mediamtx"
  "$output/node/bin/node" --version
  "$output/mediamtx/mediamtx" --version
}

create_python_env() {
  local project="$1" venv="$2" mode="$3" bundle="${4:-}"
  log 'Creating a fresh Python environment on this machine'
  [[ "$("$PYTHON" -c 'import sys; print("%s.%s" % sys.version_info[:2])')" == 3.10 ]] \
    || die 'Use the Ubuntu 22.04 system Python 3.10 at /usr/bin/python3.'
  run_as_user "$PYTHON" -m venv "$venv"
  if [[ "$mode" == offline ]]; then
    run_as_user env PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
      "$venv/bin/python" -m pip --isolated install --no-index --only-binary=:all: \
      --find-links "$bundle/python/wheels" -r "$bundle/python/requirements.lock"
  else
    run_as_user "$venv/bin/python" -m pip install -r "$DEPLOY_DIR/config/python-bootstrap.txt"
    run_as_user "$venv/bin/python" "$HELPER" requirements "$project" "$venv/requirements.in"
    run_as_user "$venv/bin/python" -m pip install -r "$venv/requirements.in"
  fi
  run_as_user "$venv/bin/python" -m pip check
  run_as_user "$venv/bin/python" -c 'import fastapi, uvicorn, pydantic_settings, sqlalchemy, httpx, multipart, reportlab, pymodbus, serial, websockets'
  check_backend "$project" "$venv"
  # The service imports app from WorkingDirectory. No editable install or copied venv is needed.
}

check_backend() {
  local project="$1" venv="$2" check_dir="$WORK_DIR/backend-check"
  mkdir -p "$check_dir"
  chown "$RUN_USER:$RUN_GROUP" "$check_dir"
  (
    cd -- "$project/server" || exit 1
    run_as_user env PYTHONPYCACHEPREFIX="$check_dir/pycache" \
      PIPESIGHT_DATA_DIR="$check_dir/data" PIPESIGHT_STORAGE_DIR="$check_dir/storage" \
      PIPESIGHT_DATABASE_URL="sqlite:///$check_dir/check.db" \
      PIPESIGHT_MEDIAMTX_CONFIG="$check_dir/mediamtx.yml" \
      "$venv/bin/python" -c 'from app.main import app; print("Backend application import OK")'
  )
}

build_frontend() {
  local project="$1" tools="$2" cache="$3" mode="$4"
  local options=(ci --include=dev --cache "$cache" --no-audit --no-fund)
  [[ "$mode" == offline ]] && options+=(--offline)
  log "Building frontend ($mode, package-lock.json)"
  mkdir -p "$cache"
  chown -R "$RUN_USER:$RUN_GROUP" "$cache"
  (
    cd -- "$project/front_end" || exit 1
    run_as_user env PATH="$tools/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
      "$tools/node/bin/npm" "${options[@]}"
    run_as_user env PATH="$tools/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
      "$tools/node/bin/npm" run build
  )
  [[ -s "$project/front_end/dist/index.html" ]] || die 'Frontend build did not produce index.html.'
}

build_bridge() {
  local project="$1" output="$2"
  local sdk="$project/3d_camera/linux" libraries="$project/3d_camera/linux/libs/lib/$SDK_ARCH"
  log "Building camera bridge ($ARCH)"
  run_as_user g++ -std=c++14 -O2 -pthread \
    -I"$project/pointcloud_bridge" -I"$sdk/include" -I"$sdk/libs/include" \
    "$project/pointcloud_bridge/main.cpp" "$sdk/src/CameraSrv.cpp" \
    -L"$libraries" -Wl,-rpath-link,"$libraries" -lAngstrongCameraSdk -o "$output"
  env LD_LIBRARY_PATH="$libraries" ldd "$output" > "$output.ldd"
  if grep -q 'not found' "$output.ldd"; then
    cat "$output.ldd" >&2
    die 'Camera bridge has missing shared libraries.'
  fi
}

check_bundle() {
  local bundle="$1" key value
  [[ -f "$bundle/SHA256SUMS" && -f "$bundle/manifest.env" ]] || die "Incomplete offline bundle: $bundle"
  log 'Verifying offline bundle SHA-256 checksums'
  (cd -- "$bundle" && sha256sum --check --strict --quiet SHA256SUMS)
  local bundle_os='' bundle_version='' bundle_arch='' bundle_node='' bundle_mtx='' bundle_format=''
  # Treat metadata as data, never source it as shell code.
  while IFS='=' read -r key value; do
    case "$key" in
      FORMAT) bundle_format="$value" ;;
      OS_ID) bundle_os="$value" ;;
      OS_VERSION) bundle_version="$value" ;;
      ARCH) bundle_arch="$value" ;;
      NODE_VERSION) bundle_node="$value" ;;
      MEDIAMTX_VERSION) bundle_mtx="$value" ;;
    esac
  done < "$bundle/manifest.env"
  [[ "$bundle_format" == 1 && "$bundle_os" == ubuntu && "$bundle_version" == 22.04 && "$bundle_arch" == "$ARCH" ]] \
    || die 'Offline bundle OS/architecture does not match this machine.'
  [[ "$bundle_node" == "$NODE_VERSION" && "$bundle_mtx" == "$MEDIAMTX_VERSION" ]] || die 'Offline bundle tool versions do not match this checkout.'
  [[ -s "$bundle/debs/Packages" && -s "$bundle/python/requirements.lock" ]] || die 'Offline dependency metadata is missing.'
  [[ -f "$bundle/node/$NODE_ASSET" && -f "$bundle/mediamtx/$MTX_ASSET" && -d "$bundle/npm-cache/_cacache" ]] \
    || die 'Offline tool archives or npm cache are missing.'
}

configure_offline_apt() {
  local bundle="$1" directory="$2"
  mkdir -p "$directory/lists/partial" "$directory/archives/partial"
  cp -- "$bundle/debs/"*.deb "$directory/archives/"
  local uri="$bundle/debs"
  uri="${uri//%/%25}"
  uri="${uri// /%20}"
  uri="${uri//#/%23}"
  printf 'deb [trusted=yes] file:%s ./\n' "$uri" > "$directory/sources.list"
  OFFLINE_APT_OPTIONS=(
    -o "Dir::Etc::sourcelist=$directory/sources.list"
    -o 'Dir::Etc::sourceparts=-'
    -o "Dir::State::lists=$directory/lists"
    -o "Dir::Cache::archives=$directory/archives"
    -o 'APT::Sandbox::User=root'
    -o 'Acquire::Languages=none'
  )
}

install_system_offline() {
  local bundle="$1"
  log 'Installing system packages from the local deb repository only'
  configure_offline_apt "$bundle" "$WORK_DIR/apt"
  apt-get "${OFFLINE_APT_OPTIONS[@]}" update
  DEBIAN_FRONTEND=noninteractive apt-get "${OFFLINE_APT_OPTIONS[@]}" \
    install -y --no-download --no-install-recommends --no-remove "${SYSTEM_PACKAGES[@]}"
}

collect_debs() {
  local bundle="$1"
  log 'Downloading the complete deb dependency closure (including already-installed packages)'
  mkdir -p "$bundle/debs/partial"
  : > "$WORK_DIR/empty-dpkg-status"
  apt-get -y --download-only --no-install-recommends \
    -o "Dir::State::status=$WORK_DIR/empty-dpkg-status" \
    -o "Dir::Cache::archives=$bundle/debs" \
    -o 'APT::Sandbox::User=root' install "${SYSTEM_PACKAGES[@]}"
  (
    cd -- "$bundle/debs" || exit 1
    dpkg-scanpackages --multiversion . /dev/null > Packages
    gzip -n -k Packages
  )
  rm -f -- "$bundle/debs/lock"
  rmdir -- "$bundle/debs/partial"
}

verify_offline_apt() {
  local bundle="$1"
  log 'Checking local deb dependency closure against an empty package database'
  configure_offline_apt "$bundle" "$WORK_DIR/apt-verify"
  : > "$WORK_DIR/empty-dpkg-status"
  unshare --net apt-get "${OFFLINE_APT_OPTIONS[@]}" update
  unshare --net apt-get "${OFFLINE_APT_OPTIONS[@]}" \
    -o "Dir::State::status=$WORK_DIR/empty-dpkg-status" \
    --simulate --no-download --no-install-recommends --no-remove install "${SYSTEM_PACKAGES[@]}"
}

prepare_offline() {
  local output="$1"
  output="$(realpath -m -- "$output")"
  [[ ! -e "$output" ]] || die "Output already exists; choose a new directory: $output"
  local parent
  parent="$(dirname -- "$output")"
  [[ -d "$parent" ]] || die "Create the output parent directory first: $parent"
  install_system_online
  make_workdir
  local project="$WORK_DIR/PipeSightConsoleServer" bundle="$WORK_DIR/PipeSightConsoleServer/deploy/offline"
  "$PYTHON" "$HELPER" snapshot "$REPO_DIR" "$project" "$SDK_ARCH"
  mkdir -p "$bundle/python/wheels"
  collect_debs "$bundle"
  verify_offline_apt "$bundle"
  fetch_tools "$bundle"
  extract_tools "$bundle" "$WORK_DIR/tools"
  chown -R "$RUN_USER:$RUN_GROUP" "$project"
  create_python_env "$project" "$WORK_DIR/venv" online
  run_as_user "$WORK_DIR/venv/bin/python" -m pip freeze --all > "$bundle/python/requirements.lock"
  run_as_user "$WORK_DIR/venv/bin/python" -m pip download --only-binary=:all: \
    --dest "$bundle/python/wheels" -r "$bundle/python/requirements.lock"
  build_frontend "$project" "$WORK_DIR/tools" "$bundle/npm-cache" online
  build_bridge "$project" "$WORK_DIR/pointcloud_bridge"
  "$PYTHON" "$HELPER" manifest "$project" "$bundle" "$ARCH" "$NODE_VERSION" "$MEDIAMTX_VERSION"
  # Validate the caches with fresh environments, with networking disallowed by each package manager.
  create_python_env "$project" "$WORK_DIR/offline-venv" offline "$bundle"
  build_frontend "$project" "$WORK_DIR/tools" "$bundle/npm-cache" offline
  "$PYTHON" "$HELPER" checksums "$bundle"
  # Only source and dist are shipped. The installer recreates npm modules and venv on the target.
  rm -rf -- "$project/front_end/node_modules"
  mkdir -p "$output"
  mv -- "$project" "$output/PipeSightConsoleServer"
  local archive="$output/PipeSightConsoleServer-ubuntu22.04-${ARCH}.tar.gz"
  tar -czf "$archive" -C "$output" PipeSightConsoleServer
  (cd -- "$output" && sha256sum "$(basename -- "$archive")" > "$(basename -- "$archive").sha256")
  chown -R "$RUN_USER:$RUN_GROUP" "$output"
  log "Offline bundle ready: $archive"
  printf 'Extract on the target, then run: sudo bash deploy/install-offline.sh\n'
}

install_permissions() {
  usermod -aG dialout,video "$RUN_USER"
  if getent group plugdev >/dev/null; then usermod -aG plugdev "$RUN_USER"; fi
  install -m 644 "$DEPLOY_DIR/udev/60-pipesight-camera.rules" /etc/udev/rules.d/60-pipesight-camera.rules
  local serial="$DEPLOY_DIR/udev/99-pipesight-serial.rules"
  if [[ -f "$serial" ]]; then
    ! has_serial_placeholders "$serial" || die 'Serial udev rules must contain actual device identifiers.'
    install -m 644 "$serial" /etc/udev/rules.d/99-pipesight-serial.rules
  else
    printf 'Serial aliases use existing udev rules or server/.env; see deploy/README.md.\n'
  fi
  udevadm control --reload-rules
  # Apply USB device permissions; avoid triggering unrelated subsystems.
  udevadm trigger --subsystem-match=usb
}

has_serial_placeholders() {
  grep -Eq '^[[:space:]]*[^#[:space:]].*__[A-Z_]+__' "$1"
}

prepare_units() {
  local release="$1"
  mkdir -p "$WORK_DIR/units"
  "$PYTHON" "$HELPER" units "$REPO_DIR" "$release" "$RUN_USER" "$RUN_GROUP" "$SDK_ARCH" "$WORK_DIR/units"
  if ! systemd-analyze verify "$WORK_DIR/units/"*.service 2> "$WORK_DIR/units/verify.log"; then
    cat "$WORK_DIR/units/verify.log" >&2
    die 'Invalid generated systemd units.'
  fi
  if grep -Fq "$WORK_DIR/units/" "$WORK_DIR/units/verify.log"; then
    cat "$WORK_DIR/units/verify.log" >&2
    die 'systemd rejected a directive in the generated units.'
  fi
}

install_units() {
  mkdir -p "$DEPLOY_DIR/systemd"
  install -m 644 "$WORK_DIR/units/"*.service "$DEPLOY_DIR/systemd/"
  install -m 644 "$WORK_DIR/units/"*.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable pipesight-backend.service pipesight-pcl-bridge.service
}

configure_firewall() {
  (( SKIP_FIREWALL )) && return 0
  if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    log 'Opening PipeSight ports in the active UFW firewall'
    ufw allow "$HTTP_PORT/tcp"
    ufw allow 8189/udp
    ufw allow 9090:9093/tcp
    # WHEP is proxied by the backend; camera RTSP/MediaMTX signaling do not need inbound rules.
  fi
}

install_project() {
  local mode="$1" bundle="${2:-}"
  require_systemd
  make_workdir
  if [[ "$mode" == online ]]; then
    install_system_online
    bundle="$WORK_DIR/downloads"
    fetch_tools "$bundle"
  else
    if [[ -x "$PYTHON" ]]; then "$PYTHON" "$HELPER" validate "$REPO_DIR" "$bundle"; fi
    install_system_offline "$bundle"
    "$PYTHON" "$HELPER" validate "$REPO_DIR" "$bundle"
  fi
  local release
  release="$RUNTIME_DIR/releases/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  run_as_user mkdir -p "$release"
  chown "$RUN_USER:$RUN_GROUP" "$RUNTIME_DIR" "$RUNTIME_DIR/releases" "$release"
  extract_tools "$bundle" "$release"
  create_python_env "$REPO_DIR" "$release/venv" "$mode" "$bundle"
  local build_project="$WORK_DIR/project"
  mkdir -p "$build_project/front_end"
  # Exclude existing dependency and build directories while copying.
  tar -C "$FRONT_DIR" --exclude=./node_modules --exclude=./dist --exclude=./.env \
    -cf - . | tar -C "$build_project/front_end" -xf -
  chown -R "$RUN_USER:$RUN_GROUP" "$build_project"
  local npm_cache="$WORK_DIR/npm-cache"
  if [[ "$mode" == offline ]]; then cp -a -- "$bundle/npm-cache" "$npm_cache"; fi
  build_frontend "$build_project" "$release" "$npm_cache" "$mode"
  build_bridge "$REPO_DIR" "$release/pointcloud_bridge"
  run_as_user env PYTHONPYCACHEPREFIX="$WORK_DIR/pycache" \
    "$release/venv/bin/python" -m compileall -q "$SERVER_DIR/app"
  if [[ -f "$DEPLOY_DIR/udev/99-pipesight-serial.rules" ]]; then
    ! has_serial_placeholders "$DEPLOY_DIR/udev/99-pipesight-serial.rules" || die 'Serial udev rules must contain actual device identifiers.'
  fi
  local environment_file="$SERVER_DIR/.env"
  [[ -f "$environment_file" ]] || environment_file="$DEPLOY_DIR/config/backend.env"
  run_as_user test -r "$environment_file" || die "Service account $RUN_USER cannot read $environment_file; fix its ownership/permissions."
  HTTP_PORT="$(run_as_user "$release/venv/bin/python" -c 'from dotenv import dotenv_values; import sys; print(dotenv_values(sys.argv[1]).get("PIPESIGHT_PORT") or "8000")' "$environment_file")"
  [[ "$HTTP_PORT" =~ ^[0-9]+$ && "$HTTP_PORT" -ge 1 && "$HTTP_PORT" -le 65535 ]] || die 'Invalid PIPESIGHT_PORT in server/.env.'
  local health_host
  health_host="$(run_as_user "$release/venv/bin/python" -c 'from dotenv import dotenv_values; import sys; print(dotenv_values(sys.argv[1]).get("PIPESIGHT_HOST") or "0.0.0.0")' "$environment_file")"
  case "$health_host" in
    0.0.0.0|'*') health_host=127.0.0.1 ;;
    ::) health_host='[::1]' ;;
    *:*) health_host="[$health_host]" ;;
  esac
  prepare_units "$release"
  log 'Applying built artifacts and systemd configuration'
  local unit
  for unit in pipesight-backend pipesight-pcl-bridge; do
    if systemctl cat "$unit.service" >/dev/null 2>&1; then systemctl stop "$unit.service"; fi
  done
  mkdir -p "$release/previous"
  if [[ -e "$SERVER_DIR/.venv" || -L "$SERVER_DIR/.venv" ]]; then mv -- "$SERVER_DIR/.venv" "$release/previous/venv"; fi
  ln -s -- "$release/venv" "$SERVER_DIR/.venv"
  if [[ -d "$FRONT_DIR/dist" ]]; then mv -- "$FRONT_DIR/dist" "$release/previous/dist"; fi
  mv -- "$build_project/front_end/dist" "$FRONT_DIR/dist"
  if [[ -e "$BRIDGE_DIR/pointcloud_bridge" || -L "$BRIDGE_DIR/pointcloud_bridge" ]]; then
    mv -- "$BRIDGE_DIR/pointcloud_bridge" "$release/previous/pointcloud_bridge"
  fi
  ln -s -- "$release/pointcloud_bridge" "$BRIDGE_DIR/pointcloud_bridge"
  install -m 755 "$release/mediamtx/mediamtx" /usr/local/bin/mediamtx
  if [[ ! -f "$SERVER_DIR/.env" ]]; then
    install -o "$RUN_USER" -g "$RUN_GROUP" -m 600 "$DEPLOY_DIR/config/backend.env" "$SERVER_DIR/.env"
  fi
  # Writable default runtime directories; existing file ownership is preserved.
  install -d -o "$RUN_USER" -g "$RUN_GROUP" "$SERVER_DIR/data" "$SERVER_DIR/storage" "$SERVER_DIR/third_party"
  install_permissions
  install_units
  configure_firewall
  if (( ! NO_START )); then
    systemctl restart pipesight-backend.service pipesight-pcl-bridge.service
    local ready=0 attempt
    for (( attempt=1; attempt<=30; attempt++ )); do
      if curl --fail --silent --max-time 2 "http://$health_host:$HTTP_PORT/api/system/health" -o "$WORK_DIR/health.json" \
        && "$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if all(d.get(k) for k in ("ok", "ffmpeg", "mediamtx", "mediamtxRunning")) else 1)' "$WORK_DIR/health.json"; then
        ready=1
        break
      fi
      sleep 1
    done
    (( ready )) || die 'Backend/FFmpeg/MediaMTX health check failed; inspect journalctl -u pipesight-backend -n 80.'
    systemctl is-active --quiet pipesight-backend.service pipesight-pcl-bridge.service \
      || die 'A service failed; inspect systemctl status and journalctl.'
  fi
  log "Installation complete: http://<machine-ip>:$HTTP_PORT"
  printf 'Service account: %s\nArtifacts: %s\n' "$RUN_USER" "$release"
  printf 'Logs: journalctl -u pipesight-backend -u pipesight-pcl-bridge -f\n'
}

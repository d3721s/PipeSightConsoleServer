#!/bin/bash
# Build the PipeSight point-cloud bridge.
#
# Compiles main.cpp + the SDK's CameraSrv.cpp and links against the Angstrong
# camera SDK shared libs (x86_64). Zero extra dependencies beyond g++ and the
# SDK that already ships under ../3d_camera/linux.
#
# Usage:  ./build.sh
set -e

CUR_DIR="$(dirname "$(readlink -f "$0")")"
SDK_DIR="$CUR_DIR/../3d_camera/linux"
LIB_DIR="$SDK_DIR/libs/lib/x86_64-linux-gnu"

if [ ! -d "$SDK_DIR" ]; then
  echo "ERROR: SDK dir not found at $SDK_DIR" >&2
  exit 1
fi

echo "Compiling pointcloud_bridge..."
g++ -std=c++14 -O2 -pthread \
  -I"$CUR_DIR" \
  -I"$SDK_DIR/include" \
  -I"$SDK_DIR/libs/include" \
  "$CUR_DIR/main.cpp" \
  "$SDK_DIR/src/CameraSrv.cpp" \
  -L"$LIB_DIR" \
  -lAngstrongCameraSdk \
  -Wl,-rpath,"$LIB_DIR" \
  -o "$CUR_DIR/pointcloud_bridge"

echo "Done -> $CUR_DIR/pointcloud_bridge"
echo "Run with: ./run.sh"

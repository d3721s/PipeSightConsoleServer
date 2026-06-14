#!/bin/bash
# Run the point-cloud bridge with the SDK shared libs on the library path.
# (The binary is also built with -rpath, so this is belt-and-suspenders.)
set -e

CUR_DIR="$(dirname "$(readlink -f "$0")")"
LIB_DIR="$CUR_DIR/../3d_camera/linux/libs/lib/x86_64-linux-gnu"

export LD_LIBRARY_PATH="$LIB_DIR:$LD_LIBRARY_PATH"
exec "$CUR_DIR/pointcloud_bridge"

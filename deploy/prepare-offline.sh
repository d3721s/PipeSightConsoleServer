#!/usr/bin/env bash
#
# 准备离线部署包
# 在有网络的机器上运行此脚本，生成可在离线机器上部署的包
#
# Usage:
#   bash deploy/prepare-offline.sh
#
# 输出：
#   pipesight-offline-<date>.tar.gz - 包含前端构建结果和后端代码的离线包

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
FRONT_DIR="$REPO_DIR/front_end"
SERVER_DIR="$REPO_DIR/server"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_NAME="pipesight-offline-${TIMESTAMP}.tar.gz"

echo "==> PipeSight 离线部署包准备工具"
echo ""
echo "准备工作目录..."

# 创建临时目录
TEMP_DIR=$(mktemp -d)
PACK_DIR="$TEMP_DIR/PipeSightConsoleServer"
trap "rm -rf '$TEMP_DIR'" EXIT

echo "==> 检查前端依赖..."
if [ ! -d "$FRONT_DIR/node_modules" ]; then
    echo "前端依赖未安装，正在安装..."
    cd "$FRONT_DIR"
    npm install
    echo "✓ 前端依赖安装完成"
else
    echo "✓ 前端依赖已存在"
fi

echo ""
echo "==> 构建前端..."
cd "$FRONT_DIR"
npm run build
echo "✓ 前端构建完成"

echo ""
echo "==> 准备离线包..."
mkdir -p "$PACK_DIR"

# 复制必要的文件
echo "  复制项目文件..."
rsync -a \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'server/storage' \
    --exclude 'server/media' \
    --exclude 'node_modules/.cache' \
    "$REPO_DIR/" "$PACK_DIR/"

# 创建说明文件
cat > "$PACK_DIR/OFFLINE_DEPLOY.txt" << 'EOF'
PipeSight 离线部署包
====================

此包包含：
- 前端构建结果（front_end/dist/）
- 前端依赖（front_end/node_modules/）
- 后端代码（server/）
- 部署脚本（deploy/）

部署步骤：
---------

1. 解压此包到 Linux 机器：
   tar xzf pipesight-offline-YYYYMMDD_HHMMSS.tar.gz
   cd PipeSightConsoleServer

2. 修复脚本换行符（如果从 Windows 传输）：
   bash deploy/fix-line-endings.sh

3. 运行离线部署：
   sudo bash deploy/update.sh --back --bridge

   这会：
   - 跳过前端构建（已包含在包中）
   - 安装后端 Python 依赖
   - 编译 C++ 桥接
   - 重启服务

4. 检查服务状态：
   systemctl status pipesight-backend
   systemctl status pipesight-pcl-bridge

5. 访问：
   http://<机器IP>:8000

注意事项：
---------
- 首次部署需要先运行 deploy/install.sh 安装系统依赖
- 此离线包适用于代码更新，不适用于全新安装
- 如果需要全新安装，请参考 deploy/README.md
EOF

# 打包
echo "  打包中..."
cd "$TEMP_DIR"
tar czf "$REPO_DIR/$OUTPUT_NAME" PipeSightConsoleServer/

# 显示结果
PACK_SIZE=$(du -h "$REPO_DIR/$OUTPUT_NAME" | cut -f1)
echo ""
echo "✅ 离线部署包已生成："
echo ""
echo "   文件: $OUTPUT_NAME"
echo "   大小: $PACK_SIZE"
echo "   位置: $REPO_DIR"
echo ""
echo "传输此文件到 Linux 机器，解压后按 OFFLINE_DEPLOY.txt 说明操作。"
echo ""

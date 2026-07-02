#!/usr/bin/env bash
#
# 离线部署脚本 - 在无网络的 Linux 机器上使用
#
# 前提：已从有网机器上运行 prepare-offline.sh 生成部署包并解压
#
# Usage:
#   sudo bash deploy/deploy-offline.sh
#
# 此脚本会：
#   1. 检查前端构建结果是否存在
#   2. 只更新后端和桥接（跳过前端构建）
#   3. 重启服务

set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 sudo 运行: sudo bash deploy/deploy-offline.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
FRONT_DIR="$REPO_DIR/front_end"
DIST_DIR="$FRONT_DIR/dist"

echo "==> PipeSight 离线部署"
echo ""

# 检查前端构建结果
if [ ! -d "$DIST_DIR" ] || [ ! -f "$DIST_DIR/index.html" ]; then
    echo "错误：未找到前端构建结果 ($DIST_DIR)"
    echo ""
    echo "请确保："
    echo "  1. 已使用 prepare-offline.sh 生成离线包"
    echo "  2. 已完整解压离线包"
    echo "  3. front_end/dist/ 目录存在"
    echo ""
    exit 1
fi

echo "✓ 前端构建结果已存在"
echo ""

# 检查 node_modules（可选，但有助于未来需要时）
if [ ! -d "$FRONT_DIR/node_modules" ]; then
    echo "⚠ 警告: node_modules 不存在"
    echo "  如果未来需要重新构建前端，请从有网机器复制 node_modules"
    echo ""
fi

# 检查是否首次安装
if [ ! -f "/etc/systemd/system/pipesight-backend.service" ]; then
    echo "⚠ 警告: 未检测到已安装的服务"
    echo ""
    echo "看起来这是首次部署。首次部署需要："
    echo "  1. 安装系统依赖（ffmpeg, fonts, python3-venv 等）"
    echo "  2. 配置 systemd 服务"
    echo ""
    echo "建议："
    echo "  - 如果系统依赖已安装，运行: sudo bash deploy/install.sh"
    echo "  - 或参考 deploy/README.md 手动配置"
    echo ""
    read -p "继续离线部署？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "==> 执行离线更新（跳过前端构建）..."
echo ""

# 调用 update.sh，只更新后端和桥接
bash "$SCRIPT_DIR/update.sh" --back --bridge

echo ""
echo "✅ 离线部署完成"
echo ""
echo "服务状态："
systemctl --no-pager --lines=0 status pipesight-backend.service || true
echo ""
echo "访问: http://$(hostname -I | awk '{print $1}'):8000"
echo "日志: journalctl -u pipesight-backend -f"

# Ubuntu 22.04 部署

部署入口只有两个：`install-online.sh` 联网安装，`install-offline.sh` 使用本地依赖包安装。两者共用配置、构建流程和 systemd 模板，也用于后续更新。

支持 Ubuntu 22.04 的 amd64（x86_64）和 arm64（AArch64）。准备离线包的机器必须与目标机器的 Ubuntu 版本、架构一致，使用系统 Python 3.10；amd64 包不能用于 arm64。Windows 可以存放源码和安装包，准备、安装均在 Ubuntu 中执行。

## 目录

```text
deploy/
├── install-online.sh             # 联网安装 / 准备离线发行包
├── install-offline.sh            # 完全使用本地依赖安装
├── config/
│   ├── versions.env              # 固定 Node、MediaMTX 版本
│   ├── system-packages.txt       # Ubuntu 系统依赖
│   └── python-bootstrap.txt      # Python 安装工具
├── lib/                          # 两个入口共用的实现
├── templates/
│   ├── systemd/                  # 自动填入路径和服务用户
│   └── udev/                     # 串口绑定规则示例
├── tests/                        # 部署逻辑校验
├── tools/uninstall.sh            # 移除 systemd 服务
└── offline/                      # 打包生成的依赖，忽略 Git
```

Python 应用依赖直接读取 `server/pyproject.toml`，前端依赖使用 `front_end/package-lock.json`。离线包记录实际 Python 版本和依赖版本，并校验源码依赖文件的 SHA-256；更改依赖后需要重新准备。

## 联网安装

将完整项目放在服务用户可读取、可写入的固定目录中，然后执行：

```bash
cd ~/PipeSightConsoleServer
bash deploy/install-online.sh --dry-run
sudo bash deploy/install-online.sh
```

脚本会安装 Ubuntu 依赖、下载并校验官方 Node / MediaMTX，创建 Python 虚拟环境，执行 `npm ci` 并构建前端，编译对应架构的相机桥接程序，安装并启用两个 systemd 服务。安装结束会检查 HTTP 健康接口和服务状态。

默认服务账户是执行 `sudo` 的用户；以 root 登录时必须用 `--user` 指定已存在的普通用户：

```bash
sudo bash deploy/install-online.sh --user robot
```

## 准备离线包（有网时）

在与目标机相同版本、架构的 Ubuntu 上运行。准备过程会安装构建依赖，但不会安装或启动 PipeSight 服务。输出目录必须尚不存在，其父目录必须存在：

```bash
mkdir -p ~/pipesight-releases
cd ~/PipeSightConsoleServer
sudo bash deploy/install-online.sh --prepare-offline ~/pipesight-releases/release-001
```

生成源码目录和两个可拷走的文件：

```text
release-001/
├── PipeSightConsoleServer/                         # 源码与离线依赖目录
├── PipeSightConsoleServer-ubuntu22.04-amd64.tar.gz  # arm64 会使用对应文件名
└── PipeSightConsoleServer-ubuntu22.04-amd64.tar.gz.sha256
```

压缩包包含应用源码、对应架构相机 SDK 和以下全部依赖：

| 依赖 | 离线内容 / 安装方式 |
| --- | --- |
| Ubuntu | `.deb` 的完整递归依赖，包括准备机已经装过的包；创建本地 APT 仓库 |
| Python | 全部依赖的 wheel 与固定版本清单；`pip --no-index` 安装 |
| Node.js | 固定版本的官方 Linux 二进制归档 |
| 前端 | `package-lock.json` 对应的 npm 缓存；`npm ci --offline` 后重新构建 |
| MediaMTX | 固定版本的对应架构官方二进制归档 |

打包时会校验本地 APT 仓库在空包数据库下的依赖解析，并重新创建 Python 环境、执行离线 npm 构建。APT 校验使用独立网络命名空间，需要普通 Ubuntu 的 `unshare --net` 能力；受限容器中应改用虚拟机或目标机准备。压缩包不携带 `.env`、数据库、录像、Windows 虚拟环境或 `node_modules`。

## 离线安装（可以完全断网）

拷贝 `.tar.gz` 和 `.sha256` 到目标 Ubuntu。以将来运行服务的普通用户解压到固定目录，再用 sudo 安装：

```bash
sha256sum -c PipeSightConsoleServer-ubuntu22.04-amd64.tar.gz.sha256
tar -xzf PipeSightConsoleServer-ubuntu22.04-amd64.tar.gz
cd PipeSightConsoleServer
bash deploy/install-offline.sh --dry-run
sudo bash deploy/install-offline.sh
```

安装器首先验证依赖包校验和、系统架构和依赖文件。APT 只加载本地 `file:` 源，pip 禁用索引，npm 使用离线模式；缺包会直接报错。虚拟环境和桥接程序在目标机重新创建。

如果已有源码目录，只搬入离线依赖，可通过 `--bundle /绝对路径/offline` 指定。依赖包必须与当前源码的依赖文件一致。

## 通用参数与更新

| 参数 | 作用 |
| --- | --- |
| `--user USER` | 指定已有的非 root 服务账户 |
| `--dry-run` | 检查环境并显示计划；离线模式同时检查依赖包 |
| `--no-start` | 安装并启用服务，但不启动；更新时会停止已有服务 |
| `--skip-firewall` | 不修改已有 UFW 规则 |
| `--help` | 查看入口用法 |

更新源码后重跑相应入口。离线更新需要新版本源码及匹配的离线包。脚本保留已有 `server/.env`、`server/data`、`server/storage`，先完成构建和配置检查，再停止服务并替换运行产物。每次安装的产物在 `.deploy/releases/` 中，原有 venv、前端 dist、桥接程序保存在本次目录的 `previous/` 下，便于人工恢复；应用数据另行备份。安装目录应保持不变，移动目录后重新运行安装器。

## 配置、硬件与访问

首次安装从 `server/.env.example` 创建 `server/.env`。编辑相机地址、串口、存储路径等后执行：

```bash
sudo systemctl restart pipesight-backend
```

`pipesight-backend` 提供 API、静态前端并管理 MediaMTX；`pipesight-pcl-bridge` 提供相机 WebSocket 数据流。默认浏览器地址 `http://<设备IP>:8000`。若 UFW 已启用，脚本开放 HTTP 端口（默认 8000/TCP）、8189/UDP 和 9090–9093/TCP；其他防火墙需自行配置相同端口。

脚本安装 SDK 自带的相机 USB 规则，并将服务用户加入 `dialout`、`video` 等硬件组。串口设备身份必须按现场硬件配置，不能从占位符推断：

```bash
udevadm info -a -n /dev/ttyUSB0
cp deploy/templates/udev/99-pipesight-serial.rules.example deploy/config/99-pipesight-serial.rules
# 填写实际标识，选用一种匹配方式，删除多余的有效规则
sudo bash deploy/install-offline.sh    # 或 install-online.sh
```

配置规则存在时才会安装；有效规则含未填写占位符时拒绝安装。重新插拔串口后检查 `/dev/ttyUSB-Chassis` 和 `/dev/ttyUSB-IMU`，也可在 `.env` 直接指定现有设备路径。

## 运维与卸载

```bash
systemctl status pipesight-backend pipesight-pcl-bridge
journalctl -u pipesight-backend -u pipesight-pcl-bridge -f
curl http://127.0.0.1:8000/api/system/health
sudo systemctl restart pipesight-backend pipesight-pcl-bridge
sudo bash deploy/tools/uninstall.sh
```

卸载工具只移除两个 systemd 服务，保留源码、依赖、配置和应用数据。

部署逻辑校验：

```bash
python3 -m unittest discover -s deploy/tests -v
for script in deploy/install-*.sh deploy/lib/*.sh deploy/tools/*.sh; do
  bash -n "$script" || exit 1
done
```

# PipeSight 实机部署

部署目标为 Ubuntu 22.04 x86_64，实际部署账户为 `robot`，两个安装器默认使用该账户。安装、离线包准备和服务管理均在 Linux 终端中执行。离线依赖直接放在本项目的 `deploy/offline/`。systemd 文件由安装器按照目标机器的用户、架构和实际安装路径生成，保存到 `deploy/systemd/`，并原样安装到 `/etc/systemd/system/`。

在目标机器以 `robot` 登录后运行 `sudo` 安装，按终端提示输入登录密码。密码无需配置到脚本、环境文件或 systemd 文件中。`robot` 必须是已存在且可使用 `sudo` 的账户；使用 root 安装时同样默认让服务以 `robot` 运行。

## 文件结构

```text
deploy/
├── install-online.sh             # 联网安装 / 准备离线发行包
├── install-offline.sh            # 使用当前目录的离线依赖部署
├── config/
│   ├── backend.env               # 实际后端运行配置
│   ├── versions.env              # Node、MediaMTX 固定版本
│   ├── system-packages.txt       # 系统依赖清单
│   └── python-bootstrap.txt      # Python 安装工具依赖
├── systemd/                      # 安装时在目标机器生成的完整服务配置
├── udev/60-pipesight-camera.rules # 相机 SDK 提供的设备权限规则
├── lib/                          # 两个安装入口共用的实现
├── tests/                        # 部署逻辑校验
├── tools/uninstall.sh
└── offline/
    ├── debs/                     # Ubuntu deb 包及本地 APT 索引
    ├── python/                   # wheels 和固定依赖版本
    ├── node/                     # 官方 Linux Node 归档及校验文件
    ├── npm-cache/                # package-lock.json 对应的 npm 缓存
    ├── mediamtx/                 # 官方二进制归档及校验文件
    ├── manifest.env              # 系统、架构及源码依赖指纹
    └── SHA256SUMS                # 全部依赖文件的校验和
```

## Linux 离线部署

将包含 `deploy/offline/` 的完整项目放到目标 Linux 机器，在项目根目录执行：

```bash
bash deploy/install-offline.sh --dry-run
sudo bash deploy/install-offline.sh
```

安装器验证 SHA-256、Ubuntu 版本、架构和源码依赖指纹，使用本地 APT 源、`pip --no-index`、`npm ci --offline` 安装和构建，随后启动两个真实的 systemd 服务。

Ubuntu 默认使用项目的 `.deploy/releases/` 保存运行依赖，也可通过 `PIPESIGHT_DEPLOY_RUNTIME_DIR` 指定目录。项目中的 `server/.venv` 和桥接程序指向本次安装产物。安装器会根据目标机器的路径重新生成服务文件，并使用 `robot` 的实际主组，不假定用户名与主组同名。准备机器生成的 `deploy/systemd/` 文件不带入离线发行包，避免携带准备机器的账户和路径。

前端构建结果在 `front_end/dist/`，由后端托管。首次安装使用 `config/backend.env` 创建实际的 `server/.env`；重装保留已有 `.env`、数据库和媒体文件。原有 venv、dist、桥接程序保存在本次安装目录的 `previous/` 中。

## 服务与访问

```bash
systemctl status pipesight-backend pipesight-pcl-bridge
journalctl -u pipesight-backend -u pipesight-pcl-bridge -f
curl http://127.0.0.1:8000/api/system/health
sudo systemctl restart pipesight-backend pipesight-pcl-bridge
```

本机浏览器访问 `http://127.0.0.1:8000`；其他设备使用 Linux 机器的 IP 地址访问。两个服务由 systemd 管理，已启用开机自启动。默认 HTTP 为 8000/TCP，WebRTC 媒体为 8189/UDP，相机 WebSocket 为 9090–9093/TCP。已启用 UFW 时安装器放行这些端口，可用 `--skip-firewall` 保留现有防火墙规则。

## 硬件配置

相机权限使用 SDK 提供的真实设备规则；服务用户加入 `dialout`、`video` 等硬件组。后端按配置连接 `/dev/ttyUSB-Chassis` 与 `/dev/ttyUSB-IMU`。当前软件部署验证时未接入这些硬件，目标机器安装后需检查实际设备路径。

硬件接入后检查实际设备：

```bash
lsusb
ls -l /dev/ttyUSB* /dev/ttyACM*
udevadm info -a -n /dev/ttyUSB0
```

如需固定串口别名，依据实际设备的 VID/PID/序列号写入 `deploy/udev/99-pipesight-serial.rules`，重跑安装器。也可以直接在 `server/.env` 中指定真实串口路径。没有设备标识时不生成串口绑定文件。

## 联网安装和准备新的离线包

```bash
sudo bash deploy/install-online.sh
mkdir -p ~/pipesight-releases
sudo bash deploy/install-online.sh --prepare-offline ~/pipesight-releases/release-002
```

离线包必须在与目标机相同 Ubuntu 版本、架构的 Linux 上准备。准备机器也默认使用 `robot`；账户不同时通过 `--user` 指定该机器已有的非 root 账户，目标机器安装仍默认使用 `robot`。目前依赖对应 Ubuntu 22.04 amd64、Python 3.10；arm64 需要在对应架构上另行准备。系统包收集包括准备机已安装的软件及递归依赖，打包前校验本地 APT 的完整依赖解析，并验证 Python、npm 的离线安装。

依赖目录较大，已加入 Git 忽略规则，但保留在当前项目中供断网安装。修改 Python、前端或系统依赖后应重新准备对应包。

## 检查与卸载

```bash
python3 -m unittest discover -s deploy/tests -v
for script in deploy/install-*.sh deploy/lib/*.sh deploy/tools/*.sh; do
  bash -n "$script" || exit 1
done
sudo bash deploy/tools/uninstall.sh
```

卸载只移除两个 systemd 服务，保留配置、代码、依赖和应用数据。

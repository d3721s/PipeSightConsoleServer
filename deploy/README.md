# PipeSight 部署与开机自启（Ubuntu 22.04）

整套系统在一台 Ubuntu 22.04（小车工控机）上运行，开机自动拉起。用 **systemd** 管理（崩溃自动重启、开机自启、统一日志）。

## 进程构成

| 服务 | 内容 | 端口 |
|---|---|---|
| `pipesight-backend` | FastAPI(uvicorn)：API + 前端页面 + storage 静态文件；**进程内自动拉起 MediaMTX**；连接里程TCP / 底盘Modbus / IMU串口 | 8000(HTTP)、8554/8889(MediaMTX)、8189/udp(WebRTC媒体) |
| `pipesight-pcl-bridge` | 深度相机点云 C++ 桥接 → WebSocket | 9090(ws) |
| 前端 | 构建一次到 `front_end/dist/`，由后端在 `:8000` 托管，**无独立进程** | — |

> 平板浏览器只需打开 `http://<小车IP>:8000`，其余全在小车本机。

## 一键安装

```bash
cd ~/PipeSightConsoleServer
sudo bash deploy/install.sh
```

`install.sh` 会做：
1. 装系统依赖（ffmpeg、中文字体、python venv、g++、node/npm）；
2. **自动下载安装 MediaMTX**（检测架构，从 GitHub 取最新版到 `/usr/local/bin/mediamtx`）；
3. 把当前用户加入 `dialout` 组（串口权限）；
4. 构建前端（`npm run build` → `dist/`）；
5. 建后端 venv、装依赖（`pip install -e .`，含 reportlab/pymodbus/pyserial 等）；
6. 编译 C++ 点云桥接；
7. 安装并 **enable + start** 两个 systemd 服务（开机自启）；
8. **自动放行防火墙端口**（仅当 ufw 处于 active）。

**拉新代码后**重跑同一条命令即可重建并重启所有服务。

## 安装前/后须知

1. **串口 udev 绑定**：底盘 `/dev/ttyUSB-Chassis`、IMU `/dev/ttyUSB-IMU` 需你用 udev 规则固定。装完若串口连不上，**重启一次**让 `dialout` 组生效。
2. **MediaMTX**：脚本会自动下载（需联网）。若机器**离线**，请手动把对应架构的 `mediamtx` 放到 `/usr/local/bin/mediamtx` 或 `server/third_party/mediamtx/mediamtx`，脚本检测到已存在就跳过下载。
3. **防火墙**：ufw active 时脚本自动放行 8000/8889/8554/tcp、8189/udp、9090/tcp。若你用别的防火墙，手动放行这些端口（**8189/udp 是 WebRTC 媒体流，必放**）。
4. **存储路径**：默认 `server/storage`。要存 U 盘在 Web「设置 → 存储路径」里改，改完会自动重启后端（systemd 管理下也生效）。

## 常用运维命令

```bash
# 状态
systemctl status pipesight-backend
systemctl status pipesight-pcl-bridge

# 实时日志
journalctl -u pipesight-backend -f
journalctl -u pipesight-pcl-bridge -f

# 重启 / 停止 / 启动
sudo systemctl restart pipesight-backend
sudo systemctl stop pipesight-pcl-bridge
sudo systemctl start pipesight-pcl-bridge

# 关闭开机自启
sudo systemctl disable pipesight-backend pipesight-pcl-bridge
```

## 卸载

```bash
sudo bash deploy/uninstall.sh
```

## 改了 .env 后

后端的环境变量在 `server/.env`，改完重启后端：
```bash
sudo systemctl restart pipesight-backend
```

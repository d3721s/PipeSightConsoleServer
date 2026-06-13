# PipeSight Console Server

首版范围：

- 两台大华乐橙相机：前摄、后摄。
- 每台相机两个通道：`channel=1` 云台，`channel=2` 固定。
- 只使用高清主码流 `subtype=0`。
- RTSP 视频预览，ONVIF PTZ 控制，数字变焦，拍照，录像，报告 PDF。
- 服务端目标环境：Ubuntu 22.04。
- 平板目标分辨率：2560 x 1600，横屏优先。

## Ubuntu 22.04 运行

安装系统依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg nodejs npm
```

安装 MediaMTX：

```bash
# 方式一：把 mediamtx 放到 PATH
sudo install -m 755 mediamtx /usr/local/bin/mediamtx

# 方式二：放到项目内
mkdir -p server/third_party/mediamtx
cp mediamtx server/third_party/mediamtx/mediamtx
chmod +x server/third_party/mediamtx/mediamtx
```

后端：

```bash
cd server
cp .env.example .env
./run.sh
```

如果 `.venv` 是从其他系统拷贝来的，脚本会自动删除并重建 Ubuntu 虚拟环境。也可以手动执行：

```bash
cd server
rm -rf .venv
python3 -m venv .venv
./run.sh
```

前端开发：

```bash
cd front_end
./run.sh
```

访问：

```text
http://服务端IP:5173
```

## 生产运行

构建前端：

```bash
cd front_end
npm install
npm run build
```

启动后端并由 FastAPI 托管前端构建产物：

```bash
cd ../server
./run.sh
```

访问：

```text
http://服务端IP:8000
```

## 配置

后端读取 `server/.env`，常用项：

```text
PIPESIGHT_HOST=0.0.0.0
PIPESIGHT_PORT=8000
PIPESIGHT_FFMPEG_EXE=ffmpeg
PIPESIGHT_MEDIAMTX_EXE=/usr/local/bin/mediamtx
PIPESIGHT_MEDIAMTX_CONFIG=./third_party/mediamtx/mediamtx.yml
PIPESIGHT_MEDIAMTX_RTSP_PORT=8554
PIPESIGHT_MEDIAMTX_WEBRTC_PORT=8889
```

如果 `PIPESIGHT_MEDIAMTX_EXE` 未设置，后端会依次查找：

1. `PATH` 中的 `mediamtx`
2. `server/third_party/mediamtx/mediamtx`

## 开发校验

后端：

```bash
cd server
source .venv/bin/activate
python -m compileall app
```

前端：

```bash
cd front_end
npm run build
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/system/health
```

## 关键接口

- `GET /api/system/health`
- `GET /api/cameras`
- `PUT /api/cameras/{front|rear}/config`
- `POST /api/cameras/{front|rear}/probe-onvif`
- `POST /api/cameras/active`
- `GET /api/cameras/active/stream`
- `POST /api/snapshots`
- `POST /api/recordings/start`
- `POST /api/recordings/stop`
- `POST /api/reports/{id}/export-pdf`
- `WS /ws/camera-control`

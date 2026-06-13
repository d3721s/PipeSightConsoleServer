# PipeSight 管道检测系统 — Web 架构设计与实施计划

> 版本：v0.1（2026-06-12）
> 前置阅读：`doc/小车软件功能界面(1).docx`（界面需求/竞品参考）、`doc/92b340242c6b06d00c98a31a70391dc6.jpg`（功能矩阵）、`PipeSightConsole/`（旧 Qt 实现，作为硬件控制方式的参考）

---

## 1. 背景与定位

旧版是 Qt/QML 桌面程序，结构是"硬件控制台"：以设备为中心（相机面板、底盘面板、配置面板），业务数据（项目、标记、报告）是附属。

客户实际要的是**业务系统**，主线是：

```
新建检测项目（信息收集）
   → 现场作业（开车 / 看视频 / 拍照 / 标记缺陷 / 录像，硬件控制只是作业的工具）
      → 检测资产沉淀（录像、照片、标记点，全部关联 项目 + 管道里程）
         → 报告中心（轨迹报告、缺陷标记报告，导出 Word/PDF/Excel）
```

Web 化的收益：

- **业务流程天然适合 Web**：项目管理、报告中心、回放标记编辑都是典型的 CRUD + 媒体浏览页面。
- **多端访问**：平板/笔记本浏览器直接打开，不用装 Qt 程序；后续可多人同时看（操作员开车，工程师在旁边标记）。
- **业务与硬件解耦**：硬件协议全部收敛到服务端的 driver 适配层，换相机/换底盘协议不影响前端和业务逻辑。

---

## 2. 总体架构

```
┌─────────────────────── 管道机器人小车 ───────────────────────┐
│  前 IP 相机 ──RTSP──┐      ┌── 底盘控制器（TCP 0xA55A 自定义帧）│
│  后 IP 相机 ──RTSP──┤      ├── 双目相机                        │
│                     │      └── 激光雷达                        │
└─────────────────────┼──────────────┬─────────────────────────┘
                      │  无线/有线链路 │
┌─────────────────────┼──────────────┼─────── 地面站（Windows）──┐
│              ┌──────▼──────┐  ┌────▼─────────────────────┐    │
│              │  MediaMTX   │  │  业务后端 (FastAPI)        │    │
│              │  流媒体网关  │  │  - REST API（业务/配置）   │    │
│              │  RTSP 拉流  │◄─┤  - WebSocket（控制/遥测）  │    │
│              │  → WebRTC   │  │  - ffmpeg 录像/抓拍/OSD    │    │
│              │  → HLS(备用)│  │  - drivers: PTZ/底盘协议   │    │
│              └──────┬──────┘  │  - SQLite（项目/标记/报告） │    │
│                     │         └────┬─────────────────────┘    │
└─────────────────────┼──────────────┼──────────────────────────┘
                WebRTC│(视频)    HTTP│+ WebSocket（控制/数据）
              ┌───────▼──────────────▼────────┐
              │   浏览器前端 (Vue 3 SPA)        │
              │   控制台 / 项目管理 / 报告中心   │
              └───────────────────────────────┘
```

### 关键技术决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | 浏览器播 RTSP 必须经网关；选 **MediaMTX**（单 exe，免安装），RTSP → **WebRTC(WHEP)** | 浏览器不支持 RTSP。WebRTC 延迟 200–500ms，满足遥操作；相机出 H.264 可免转码直接转封装，CPU 占用极低。HLS 作为兼容备用（延迟大，仅回看用） |
| D2 | **录像/抓拍在服务端做**（ffmpeg 另起 RTSP 会话），不在浏览器做 | 与旧 Qt 方案一致（ffmpeg 参数可直接移植）；浏览器关掉/刷新不中断录像；OSD 烧录（drawtext）继续可用 |
| D3 | 控制命令走 **WebSocket**（PTZ、底盘运动、灯光），业务 CRUD 走 **REST** | 控制需要低延迟、双向、心跳保活；按住/松开（连续控制）天然是流式语义 |
| D4 | 业务库用 **SQLite**（SQLAlchemy ORM） | 地面站单机部署，零运维；ORM 隔离，将来要多站点汇总再迁 PostgreSQL |
| D5 | 硬件协议收敛到 **drivers 适配层**（接口 + 实现） | PTZ 当前协议待确认（见 §9 问题1），无论最终是 TCP 自定义帧 / ONVIF / HTTP CGI，只改 driver 不动业务 |
| D6 | 前端 **Vue 3 + TypeScript + Vite + Pinia + Element Plus** | 生态成熟、组件库齐全（表格/表单/对话框，业务页面开发快） |

---

## 3. 代码仓库结构（目标）

```
PipeSightConsoleServer/
├── doc/                  # 需求与设计文档
├── PipeSightConsole/     # 旧 Qt 工程（只读参考，不再开发）
├── server/               # 业务后端 (Python / FastAPI)
│   ├── app/
│   │   ├── main.py             # 应用入口、生命周期（启停 MediaMTX 等）
│   │   ├── api/                # REST 路由
│   │   │   ├── cameras.py      #   相机配置 / 码流 / PTZ / 抓拍
│   │   │   ├── recordings.py   #   录像 启/停/列表
│   │   │   ├── vehicle.py      #   底盘配置（M2）
│   │   │   ├── projects.py     #   项目（M4）
│   │   │   ├── markers.py      #   标记点（M3）
│   │   │   └── reports.py      #   报告（M4）
│   │   ├── ws/                 # WebSocket 端点
│   │   │   ├── control.py      #   /ws/control  下行控制（PTZ/运动/灯光）
│   │   │   └── telemetry.py    #   /ws/telemetry 上行遥测（姿态/速度/电量/信号/里程）
│   │   ├── services/           # 业务服务层
│   │   │   ├── camera.py       #   RTSP URL 构建、配置管理（移植 CameraService）
│   │   │   ├── stream_gateway.py #  MediaMTX 进程与路径管理
│   │   │   ├── recorder.py     #   ffmpeg 录像/抓拍/OSD（移植 RecordingService）
│   │   │   └── telemetry.py    #   遥测缓存与分发（移植 VehicleService 读侧）
│   │   ├── drivers/            # 硬件协议适配层
│   │   │   ├── base.py         #   PtzDriver / ChassisDriver 抽象接口
│   │   │   ├── frame_codec.py  #   0xA55A + CRC16-CCITT 帧编解码（移植 ProtocolCodec）
│   │   │   └── ptz_tcp.py      #   TCP PTZ 实现（协议待确认，见 §9）
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── db.py
│   │   └── config.py           # 服务端配置（端口、存储根目录、MediaMTX 路径）
│   ├── third_party/mediamtx/   # mediamtx.exe + mediamtx.yml
│   ├── tests/
│   └── pyproject.toml
├── front_end/            # 前端 (Vue 3 + TS + Vite)
│   ├── src/
│   │   ├── pages/
│   │   │   ├── console/        # 控制台（主操作屏：视频+PTZ+录像+小车控制）
│   │   │   ├── projects/       # 项目管理（M4）
│   │   │   ├── reports/        # 报告中心（M4）
│   │   │   ├── playback/       # 回放与标记编辑（M5）
│   │   │   └── settings/       # 系统设置（相机/底盘/雷达/录像/OSD 配置）
│   │   ├── components/
│   │   │   ├── WebRtcPlayer.vue    # WHEP 播放器（核心组件）
│   │   │   ├── PtzPad.vue          # 云台方向盘（按住连续/点按步进）
│   │   │   └── TelemetryBar.vue    # 小车状态条
│   │   ├── api/                # REST 封装（自动生成或手写 typed client）
│   │   ├── ws/                 # WebSocket 封装（重连、心跳）
│   │   └── stores/             # Pinia
│   └── package.json
└── ros/                   # 车端（用途待确认，见 §9 问题5）
```

---

## 4. 与旧 Qt 代码的映射（控制方式的迁移依据）

| 旧 Qt 模块 | 关键逻辑 | Web 化去向 |
|---|---|---|
| `CameraService` | RTSP URL：`rtsp://{user}:{pass}@{ip}/cam/realmonitor?channel={ch}&subtype={0/1/2}`（大华风格，主码流/辅码流1/辅码流2） | `server/app/services/camera.py` 原样移植 |
| `CameraService::pan/zoom` | TCP 帧 type `0x10`(pan dx,dy float) / `0x11`(zoom delta)——**代码标注 TODO 占位，未真正实现厂商协议** | `server/app/drivers/ptz_tcp.py`，**协议细节需确认（§9 问题1）** |
| `ProtocolCodec` | 帧格式 `0xA55A | LEN u16 | TYPE u8 | PAYLOAD | CRC16-CCITT` | `server/app/drivers/frame_codec.py` 用 Python struct 移植 |
| `TcpClient` / `ConnectionManager` | 自动重连、心跳、命名连接 | asyncio TCP 客户端，逻辑等价移植 |
| `RecordingService` | ffmpeg 拉 RTSP 录 mp4；H.264/H.265/MJPEG + 质量/性能档位参数表；OSD 用 drawtext+textfile 实时刷新；停止用 stdin 写 `q` | `server/app/services/recorder.py`，ffmpeg 参数几乎原封移植 |
| `RecordingService::takeSnapshot` | QMediaPlayer 抓一帧存 PNG | 服务端 `ffmpeg -i rtsp -frames:v 1`（更简单可靠） |
| QML `VideoView`(MediaPlayer) | 直接播 RTSP + 1s 自动重连 | 前端 `WebRtcPlayer.vue`（WHEP）+ 断流重连 |
| `VehicleService` | 遥测：俯仰/横滚/航向、速度、里程、电量%、电压、信号%；控制：drive(throttle,steer)、灯光 0-100、归位 | M2：driver + `/ws/telemetry` 推送 + `/ws/control` 下发 |
| `AppSettings`(QSettings) | 相机/录像/OSD/底盘配置持久化 | SQLite `device_configs` 表 + REST 配置接口 |
| `OsdRenderer` | drawtext 滤镜、文本文件热更新 | 服务端等价移植（录像烧录 + 抓拍叠加） |

---

## 5. 数据模型（业务主线，M3/M4 落地）

```
projects        检测项目：名称、检测单位、地点、管径、创建时间…（对应竞品"信息收集页"）
sessions        作业会话：project_id、开始/结束时间、操作员 —— 一次下管检测
media_assets    媒体资产：session_id、类型(录像/照片/深度照片)、文件路径、
                时间戳、odometer_m（拍摄时里程）、camera(front/rear)
markers         标记点：session_id、media_asset_id(可空)、类型(裂缝/变形/错口…)、
                odometer_m、画面坐标/框选区域、备注、严重等级
telemetry_log   遥测留痕：session_id、ts、姿态/速度/里程/电量（轨迹报告数据源）
reports         报告：project_id/session_id、标题、地点、生成时间、导出文件路径
device_configs  设备配置：相机1/2(IP/账号/三码流参数)、底盘IP、雷达、录像、OSD
system_logs     操作日志/故障日志
```

> 录像、照片、标记**必须带 odometer_m（里程）**，这是管道检测业务的主键意义所在（功能矩阵"标记位置：关联里程计数据"）。

---

## 6. M1 相机模块 — 接口草案

### REST

```
GET    /api/cameras                      # 列出 front/rear 两路配置
GET    /api/cameras/{id}/config          # id ∈ {front, rear}
PUT    /api/cameras/{id}/config          # IP/账号/密码/channel + 三码流参数
GET    /api/cameras/{id}/streams         # → { webrtc: "/whep/front_main", hls: "...", rtsp: "rtsp://..." }
POST   /api/cameras/{id}/snapshot        # 服务端抓拍 → 返回 media_asset（含文件路径、里程）
POST   /api/recordings/start             # { cameraId } → 服务端 ffmpeg 开录
POST   /api/recordings/stop              # { cameraId }
GET    /api/recordings/status
GET    /api/system/health                # MediaMTX/ffmpeg/相机连通性自检
```

### WebSocket `/ws/control`（控制通道，JSON 帧）

```jsonc
// 云台连续控制：按下发 start，松开发 stop（前端按钮 press/release 映射）
{ "type": "ptz", "camera": "front", "action": "up|down|left|right|zoom_in|zoom_out|stop",
  "mode": "continuous|step", "speed": 0.5 }

// 服务端回执 / 错误
{ "type": "ack", "ref": "...", "ok": true }
```

### 前端控制台页（M1 范围，布局沿用旧 Qt 界面习惯）

```
┌─────────────────────────────────────────┬──────────────┐
│                                         │  变焦  [远──近] │
│        WebRTC 视频 (主画面)              │  前摄 | 后摄   │
│        （OSD 字幕叠加预览）              │  录像 | 拍照   │
│                                         │   云台方向盘    │
│                                         │  ↑ ← → ↓ + -  │
├─────────────────────────────────────────┴──────────────┤
│  状态条：连接状态 | 录像状态 | （M2 起：速度/里程/电量/信号） │
└────────────────────────────────────────────────────────┘
```

功能矩阵对应：六方向云台（连续/步进）、前后摄切换、录像启停、拍照、变焦滑条、双相机 IP + 三码流配置。

---

## 7. 里程碑计划

| 里程碑 | 内容 | 预估 |
|---|---|---|
| **M0 骨架** | 仓库结构、FastAPI 骨架+SQLite、Vue 骨架+路由、MediaMTX 集成与启停管理、一条 RTSP 流在浏览器播出来（打通验证） | 2–3 天 |
| **M1 相机** | 双相机配置页、三码流、WebRTC 播放+断流重连、前/后切换、PTZ 六方向（连续+步进）、服务端抓拍、服务端录像（分段/编码/存储路径配置）、OSD 烧录移植 | 1–1.5 周 |
| **M2 底盘** | 0xA55A driver 移植、前进/后退/转向（虚拟摇杆+按键）、速度档位、灯光、归位、遥测条（姿态/速度/里程/电量/信号）、低电量告警 | 1 周 |
| **M3 标记与里程** | 作业会话、拍照编辑（画框/类型标注，对应竞品"拍照编辑"页）、标记点关联里程、遥测留痕、深度相机拍照（预留 driver） | 1 周 |
| **M4 业务闭环** | 新建项目信息收集页、项目管理、报告中心、轨迹报告（轨迹表+3D 可视化可后置）、报告详情、导出 Word/PDF/Excel | 1.5 周 |
| **M5 高级** | 回放与标记编辑（时间轴）、AI 缺陷识别（预留推理接口）、系统日志、固件升级、里程计标定 | 按需排期 |

依赖关系：M0 → M1 → M2 与 M3 可并行 → M4 → M5。每个里程碑结束都有可演示的页面。

---

## 8. 部署形态（默认假设，待确认）

- 地面站 Windows 本机运行：`server`（FastAPI，:8000）+ MediaMTX（:8554/:8889）+ 前端构建产物（由 FastAPI 静态托管，浏览器开 `http://地面站IP:8000`）。
- 开发期前端 `vite dev` 独立起，代理到 8000。
- 打包：后续可用 PyInstaller/任务计划做一键启动，非当前重点。

---

## 9. 待确认问题（阻塞 M1 的标 ⚠）

| # | 问题 | 我的默认方案（若无异议） |
|---|---|---|
| ⚠1 | **PTZ 控制到底怎么下发？** 旧 Qt 里 pan/zoom 是 TCP 自定义帧（type 0x10/0x11），但代码注释明确是"占位，待厂商协议"，且 RTSP 协议本身不承载云台命令。相机看 URL 是大华风格——请确认相机品牌/型号，PTZ 走：a) 车端控制板 TCP 转发（0xA55A 帧，需给出真实帧定义）；b) 相机 ONVIF；c) 大华 HTTP CGI | 先实现 driver 抽象接口 + 0xA55A TCP 占位实现（与旧 Qt 行为一致），协议确认后只改 driver |
| ⚠2 | **视频延迟要求**：遥操作开车时可接受多少延迟？ | <500ms，用 WebRTC（MediaMTX/WHEP） |
| 3 | **技术栈**：后端 Python FastAPI + 前端 Vue3 + Element Plus + SQLite，可以吗？（还是公司要求 Node/Java/React？） | 按此执行 |
| 4 | **部署/客户端形态**：后端跑这台 Windows 地面站？客户端是 PC 浏览器还是平板？是否需要多客户端同时访问/账号体系？ | 单机地面站 + 局域网浏览器访问，先不做账号 |
| 5 | **`ros/` 目录用途**：车端是 ROS 吗？底盘遥测/控制将来走 rosbridge 还是维持 0xA55A TCP？ | 维持 TCP，driver 层预留 rosbridge 实现位 |
| 6 | **相机实物现在可用吗**？开发期若无实机，我会用 MediaMTX + ffmpeg 推一路测试流模拟双相机 | 用模拟流开发，联调留到有实机 |

---

## 附录 A：从旧 Qt 代码提取的协议契约（移植规格）

### A.1 TCP 帧格式（`ProtocolCodec`，多字节字段大端序）

```
MAGIC 0xA55A (u16) | LEN (u16) | TYPE (u8) | PAYLOAD | CRC16 (u16)
```

- `LEN` = 1 + len(PAYLOAD) + 2（TYPE 起算到 CRC 止）
- CRC16-CCITT：初值 `0xFFFF`、多项式 `0x1021`，计算范围 TYPE..PAYLOAD
- 解码器处理半包/粘包/失步重同步（丢字节直到下一个 MAGIC）、CRC 错误丢帧
- 心跳：TYPE `0x01` 周期发送，3 倍间隔无回复则强制重连；重连退避 1s 起倍增至 30s

### A.2 帧类型表（旧代码现状）

| TYPE | 方向 | 含义 | PAYLOAD |
|------|------|------|---------|
| 0x01 | → | 心跳 | 可配置 |
| 0x10 | → | 云台 pan | float dx, float dy ∈ [-1,1] ⚠ 占位 |
| 0x11 | → | 变焦 zoom | double delta ∈ [-1,1] ⚠ 占位 |
| 0x40 | → | 底盘运动 | float throttle, float steer ∈ [-1,1] |
| 0x41 | → | 目标速度 | float m/s |
| 0x50 | → | 前灯亮度 | u8 0–100 |
| 0x51 | → | 后灯亮度 | u8 0–100 |
| 0x60 | → | 归位/里程清零 | 空 |
| 0x80 | ← | 遥测 | 大端：float pitch, roll, yaw, speed, odometer, batteryV + u8 batteryPct + u8 signalPct |
| 其他 | ← | 命令回执 | — |

⚠ 注意：旧代码下行 0x10/0x11/0x40/0x41 的浮点是 `reinterpret_cast` 主机序（x86 小端）写入，而上行 0x80 解析却按大端——本身不自洽，是占位代码的痕迹。**真实字节序随协议确认一并定**。

### A.3 RTSP 取流 URL（大华风格，已验证可用的实现）

```
rtsp://{username}:{password}@{ip}/cam/realmonitor?channel={channel}&subtype={0|1|2}
```

subtype：0=主码流，1=辅码流1，2=辅码流2；被禁用的辅码流不生成 URL。前/后摄各一套配置（IP/账号/channel + 三码流分辨率/帧率），持久化于 QSettings → Web 版迁到 `device_configs` 表。

### A.4 录像 / 抓拍 ffmpeg 参数（直接移植）

- 输入：`-rtsp_transport tcp -i {url}`
- OSD 烧录：`-vf drawtext=textfile={path}:reload=1`，文本文件由定时器按 `refreshMs`（默认 1000ms）重写，内容 = 项目名/检测单位 + 时间 + 里程/速度（来自遥测），字体/字号/位置可配
- H.264 质量档：`-c:v libx264 -preset slow -crf 16 -profile:v high -pix_fmt yuv420p -c:a aac -b:a 320k -movflags +faststart`；性能档：`-preset veryfast -crf 23 -profile:v main`，音频 128k
- H.265：`libx265 -crf 20/28 -tag:v hvc1`；MJPEG：`-q:v 2/5` + pcm_s16le，容器 avi（其余 mp4）
- 优雅停止：向 ffmpeg stdin 写 `q`（保证 moov 写全），3s 超时 terminate → 1.5s kill
- 命名：`PipeSight_yyyyMMdd_HHmmss.mp4`；抓拍 `PipeSight_snapshot_yyyyMMdd_HHmmss_zzz.png`（Web 版抓拍改为 `ffmpeg -frames:v 1`，OSD 叠加逻辑同录像）
- 分段时长（segmentMinutes）配置存在但旧代码未实现滚动分段 → Web 版用 ffmpeg `-f segment` 实现

### A.5 旧版连接拓扑

命名 TCP 连接：`camera-ptz`（云台）、`vehicle`（底盘）、`depth-camera`（双目）——同一套 0xA55A 帧协议，目标 IP/端口在旧代码中**未见绑定**（也是未完成的占位）。视频与录像走 RTSP，与 TCP 控制通道完全分离。

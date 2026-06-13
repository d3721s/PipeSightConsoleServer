# PipeSight 风电叶片内腔巡检系统 - Web 架构设计与实施计划

> 版本：v0.2（2026-06-13）
> 依据：`doc/小车软件功能界面(1).docx`、界面原型图片、`PipeSightConsole/` Qt 监控相机控制软件。

---

## 1. 定位与首版范围

旧 Qt 软件已经能控制监控相机，但整体仍偏“设备控制台”。Web 版应改成偏业务的巡检系统，主流程是：

```text
启动页/设备状态
  -> 项目/叶片信息收集
  -> 进入巡检控制页
  -> 实时看相机画面、云台控制、拍照、录像
  -> 图片标记编辑
  -> 开启/停止报告记录
  -> 报告中心
  -> 报告详情与 PDF 导出
```

### 首版必须做

- 平板横屏优先的 Web 界面。
- 目标平板分辨率：`2560 x 1600`。
- 两台监控相机设备：前摄、后摄。
- 每台相机有两个 RTSP 通道：云台通道、固定通道。
- 只使用一个高清主码流，不做多码流切换，也不做辅码流配置。
- ONVIF 云台上下左右控制：短按步进、长按连续、松手停止。
- 数字变焦：仅前端画面缩放，不做光学变焦/焦距控制。
- 拍照、录像、图片标记、报告记录、PDF 导出。
- 距离字段保留，首版默认 `0`，允许手动输入。

### 首版不做

- 小车运动控制、灯光控制、速度控制。
- 电量、姿态、里程计、雷达、双目、3D 轨迹。
- 光学变焦、焦距控制、预置点。
- 账号权限、多用户协作。
- Word/Excel 导出，首版只做 PDF。

---

## 2. 设备与协议模型

### 2.1 相机设备模型

```text
前摄像头设备 front
  - channel=1 云台摄像头 ptz
  - channel=2 固定摄像头 fixed

后摄像头设备 rear
  - channel=1 云台摄像头 ptz
  - channel=2 固定摄像头 fixed
```

每台设备配置：

```text
ip
username
password
onvif_port = 80     固定
rtsp_port  = 554    默认
```

### 2.2 RTSP 视频协议

Qt 代码中已经验证的 RTSP URL 格式：

```text
rtsp://{username}:{password}@{ip}:{rtspPort}/cam/realmonitor?channel={1|2}&subtype=0&unicast=true&proto=Onvif
```

约束：

- `channel=1` 表示云台摄像头。
- `channel=2` 表示固定摄像头。
- `subtype=0` 固定使用主码流。
- Web 首版不暴露 `subtype=1/2`，不做三码流配置。
- 录像、预览、拍照都围绕主码流。

### 2.3 ONVIF 云台协议

Qt 代码对应模块：

- `src/services/onvif_ptz_controller.cpp`
- `src/services/camera_service.cpp`

实际控制流程：

```text
Device service:
  http://{ip}:80/onvif/device_service

1. GetServices
2. 获取 Media2 service 和 PTZ service 的 XAddr
3. Media2.GetProfiles
4. 优先使用 Profile000
5. PTZ.ContinuousMove
6. PTZ.Stop
```

云台速度：

```text
velocity_x = dx * 0.25
velocity_y = -dy * 0.25
space = http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace
```

交互策略：

- 短按：发送一次 `ContinuousMove`，约 120ms 后 `Stop`。
- 长按：发送 `ContinuousMove`，超时 `PT10S`，松手发送 `Stop`。
- 只对 `channel=1` 云台通道显示云台控制。
- `channel=2` 固定通道禁用云台按钮。

### 2.4 ONVIF OSD 水印

Qt 代码对应模块：

- `src/services/onvif_osd_controller.cpp`
- `src/services/osd_service.cpp`

策略：

- 优先 Media2，失败再退 Media1。
- 支持 `GetVideoSourceConfigurations` / `GetProfiles`。
- 已存在 OSD 则 `SetOSD`，不存在则 `CreateOSD`，关闭则 `DeleteOSD`。
- 首版最多两行：
  - 项目/叶片信息 + 距离。
  - 相机时间 `DateAndTime`。

首版距离来源：

- 默认 `0`。
- 拍照、标记、报告时允许手动输入。
- 后续接入里程计后再自动填充。

---

## 3. 总体架构

```text
┌──────────────────────── 摄像头设备 ────────────────────────┐
│ 前摄设备 front: channel 1 云台 / channel 2 固定              │
│ 后摄设备 rear : channel 1 云台 / channel 2 固定              │
│ RTSP 主码流 subtype=0                                        │
│ ONVIF Device/PTZ/Media/OSD, port 80                           │
└───────────────┬───────────────────────────┬────────────────┘
                │ RTSP                      │ ONVIF SOAP/HTTP
                ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Ubuntu 22.04 服务端 FastAPI                                  │
│ - REST: 项目、相机配置、拍照、录像、标记、报告、设置          │
│ - WebSocket: 云台控制、录像状态、相机连接状态                 │
│ - CameraDriver: RTSP URL、ONVIF 探测、PTZ、OSD                │
│ - MediaService: 单路高清 RTSP 拉流、WebRTC 转发、录像、抓拍   │
│ - ReportService: PDF 报告生成                                 │
│ - SQLite: 项目、会话、媒体、标记、报告、配置                  │
└───────────────┬───────────────────────────┬────────────────┘
                │ WebRTC/WHEP               │ HTTP/WebSocket
                ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 平板浏览器前端 Vue 3 SPA                                     │
│ 启动页 / 信息收集 / 控制页 / 图片编辑 / 报告中心 / 设置       │
└─────────────────────────────────────────────────────────────┘
```

### 关键技术决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 浏览器播放使用 RTSP -> WebRTC 网关 | 浏览器不能直接播 RTSP，平板需要低延迟预览。 |
| D2 | 只拉高清主码流 `subtype=0` | 辅码流清晰度不满足业务要求，首版不做多码流配置。 |
| D3 | 录像时按 Qt 思路只拉一路 RTSP，同时转发给预览 | 避免相机同时被预览和录像拉两路高清流，降低设备压力。 |
| D4 | PTZ 使用 ONVIF `ContinuousMove` + `Stop` | 与当前 Qt 监控相机控制软件一致，适配大华乐橙的实际能力。 |
| D5 | 数字变焦只在前端做 | 当前实际能力不包含可靠的光学变焦/焦距控制。 |
| D6 | 服务端运行在 Ubuntu 22.04，业务库使用 SQLite | 单机部署，零运维，后续可迁 PostgreSQL。 |
| D7 | 报告首版导出 PDF | 与当前需求确认一致。 |

---

## 4. 目标仓库结构

```text
PipeSightConsoleServer/
├── doc/
├── PipeSightConsole/              # Qt 相机控制软件，作为协议迁移依据
├── server/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── system.py          # 健康检查、设备状态
│   │   │   ├── settings.py        # 语言、存储路径、OSD 配置
│   │   │   ├── projects.py        # 项目信息收集
│   │   │   ├── sessions.py        # 一次巡检作业
│   │   │   ├── cameras.py         # 前/后摄配置、通道切换、ONVIF 探测
│   │   │   ├── snapshots.py       # 抓拍
│   │   │   ├── recordings.py      # 录像
│   │   │   ├── annotations.py     # 图片标记
│   │   │   └── reports.py         # 报告中心、PDF 导出
│   │   ├── ws/
│   │   │   ├── camera_control.py  # PTZ 按下/松开/步进
│   │   │   └── camera_status.py   # ONVIF/RTSP/录像状态
│   │   ├── services/
│   │   │   ├── camera_service.py
│   │   │   ├── stream_service.py
│   │   │   ├── recorder_service.py
│   │   │   ├── snapshot_service.py
│   │   │   ├── annotation_service.py
│   │   │   ├── report_service.py
│   │   │   └── storage_service.py
│   │   ├── drivers/
│   │   │   ├── onvif_client.py    # SOAP 封装、认证、超时、错误解析
│   │   │   ├── onvif_ptz.py       # ContinuousMove / Stop
│   │   │   ├── onvif_osd.py       # GetOSDs / SetOSD / CreateOSD
│   │   │   └── rtsp.py            # URL 构建、连通性检测
│   │   ├── models/
│   │   ├── db.py
│   │   └── config.py
│   ├── third_party/
│   │   └── mediamtx/
│   ├── tests/
│   └── pyproject.toml
├── front_end/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── HomePage.vue
│   │   │   ├── ProjectCreatePage.vue
│   │   │   ├── CameraConsolePage.vue
│   │   │   ├── SnapshotEditorPage.vue
│   │   │   ├── ReportCenterPage.vue
│   │   │   ├── ReportDetailPage.vue
│   │   │   └── SettingsPage.vue
│   │   ├── components/
│   │   │   ├── WebRtcPlayer.vue
│   │   │   ├── CameraSwitcher.vue
│   │   │   ├── PtzPad.vue
│   │   │   ├── DigitalZoom.vue
│   │   │   ├── RecordingBadge.vue
│   │   │   ├── OsdOverlay.vue
│   │   │   └── AnnotationCanvas.vue
│   │   ├── api/
│   │   ├── ws/
│   │   └── stores/
│   └── package.json
└── ros/                          # 后续小车/传感器预留，首版不做
```

---

## 5. 与 Qt 代码的迁移映射

| Qt 模块 | 已验证逻辑 | Web 后端去向 |
|---|---|---|
| `CameraService` | 前/后摄配置、RTSP URL 构建、主码流 `subtype=0`、通道 `1/2` | `services/camera_service.py` |
| `OnvifPtzController` | `GetServices`、Media2 `GetProfiles`、PTZ `ContinuousMove`、`Stop` | `drivers/onvif_ptz.py` |
| `OnvifOsdController` | Media2/Media1 OSD 读写、创建、删除 | `drivers/onvif_osd.py` |
| `RecordingService` / `RecordWorker` | 单路 RTSP 拉流、MP4 分段、预览转发、无重编码 | `services/recorder_service.py` |
| `VideoView.qml` | RTSP/UDP 播放、重连、数字变焦 | `WebRtcPlayer.vue` + `DigitalZoom.vue` |
| `CameraPanel.qml` | 前/后摄切换、云台/固定通道切换、短按/长按云台 | `CameraConsolePage.vue` |
| `AppSettings` | 相机配置、存储路径、OSD 配置 | SQLite `device_configs` / `system_settings` |

不迁移到首版：

- `VehicleService`
- `DepthCameraService`
- `Radar` 相关占位配置
- 0xA55A TCP 帧协议

---

## 6. 数据模型

```text
projects
  id
  name
  fan_model
  fan_no
  blade_model
  blade_length
  blade_factory_no
  location
  created_at

inspection_sessions
  id
  project_id
  started_at
  ended_at
  status
  report_title
  report_location

camera_devices
  id
  code              front / rear
  name              前摄 / 后摄
  ip
  username
  password
  onvif_port        固定 80
  rtsp_port         默认 554
  status
  created_at
  updated_at

camera_channels
  id
  camera_device_id
  channel_no        1 / 2
  type              ptz / fixed
  name              云台 / 固定

media_assets
  id
  project_id
  session_id
  camera_device_id
  camera_channel_id
  type              photo / video
  file_path
  thumbnail_path
  captured_at
  distance_m        默认 0，可手动输入

annotations
  id
  media_asset_id
  annotation_json   画笔、标记框、文字
  rendered_path
  created_at

markers
  id
  project_id
  session_id
  media_asset_id
  defect_type
  defect_code
  severity
  direction
  position
  note
  distance_m        默认 0，可手动输入
  created_at

reports
  id
  project_id
  session_id
  title
  location
  status
  pdf_path
  started_at
  ended_at
  exported_at

system_settings
  key
  value_json

system_logs
  id
  ts
  level
  source
  message
```

---

## 7. 接口草案

### 7.1 系统与设置

```text
GET  /api/system/health
GET  /api/system/info
GET  /api/settings
PUT  /api/settings
```

### 7.2 项目与作业

```text
POST /api/projects
GET  /api/projects
GET  /api/projects/{id}

POST /api/sessions
POST /api/sessions/{id}/finish
```

### 7.3 相机

```text
GET  /api/cameras
GET  /api/cameras/{device}/config              # device = front | rear
PUT  /api/cameras/{device}/config
POST /api/cameras/{device}/probe-onvif
GET  /api/cameras/{device}/channels            # channel 1 云台 / channel 2 固定
POST /api/cameras/active                       # { device, channel }
GET  /api/cameras/active/stream                # 当前主码流 WebRTC URL
```

配置字段只保留：

```json
{
  "ip": "192.168.71.21",
  "username": "admin",
  "password": "***",
  "onvifPort": 80,
  "rtspPort": 554
}
```

不提供多码流、分辨率、帧率配置接口，首版固定主码流。

### 7.4 云台 WebSocket

路径：

```text
/ws/camera-control
```

步进：

```json
{
  "type": "ptz_step",
  "device": "front",
  "channel": 1,
  "direction": "up|down|left|right"
}
```

连续开始：

```json
{
  "type": "ptz_start",
  "device": "front",
  "channel": 1,
  "direction": "up|down|left|right"
}
```

连续停止：

```json
{
  "type": "ptz_stop",
  "device": "front",
  "channel": 1
}
```

服务端统一转换为：

```text
ONVIF ContinuousMove / Stop
```

### 7.5 拍照、录像、标记、报告

```text
POST /api/snapshots
POST /api/recordings/start
POST /api/recordings/stop
GET  /api/recordings/status

POST /api/annotations
GET  /api/media/{id}/annotations

POST /api/markers
PUT  /api/markers/{id}
DELETE /api/markers/{id}

POST /api/reports/start
POST /api/reports/stop
GET  /api/reports
GET  /api/reports/{id}
POST /api/reports/{id}/export-pdf
```

---

## 8. 前端页面结构

### 8.1 启动页

对应原型首页：

- 历史影像
- 报告中心
- 系统设置
- 视频设置/相机状态
- 机器信息与搜索状态
- 启动机器人/开始巡检

首版“机器信息”实际展示相机和后端状态，不展示小车状态。

### 8.2 信息收集页

字段：

- 项目名称
- 风机机型
- 风机编号
- 叶片型号
- 叶片长度
- 叶片出厂编号

提交后创建 `project` 和 `inspection_session`。

### 8.3 控制页

平板横屏布局：

```text
┌───────────────────────────────────────────────┬──────────────┐
│                                               │ 返回 / 开启报告 │
│              WebRTC 高清主画面                 │ 前摄 / 后摄    │
│              OSD 水印                           │ 云台 / 固定    │
│                                               │ 拍照 / 录像    │
│                                               │ 数字变焦       │
│                                               │ 云台方向按钮   │
└───────────────────────────────────────────────┴──────────────┘
```

规则：

- `channel=1` 显示云台按钮。
- `channel=2` 禁用云台按钮。
- 数字变焦对两个通道都可用。
- 距离显示默认 `0m`，可在拍照/标记时手动改。

### 8.4 拍照编辑页

功能：

- 选择
- 画笔
- 标记框
- 文字
- 撤销
- 清空
- 保存图片
- 标记并保存
- 距离手动输入，默认 `0`

### 8.5 报告中心

功能：

- 报告列表
- 删除报告
- 查看报告
- 查看轨迹/记录
- PDF 导出

### 8.6 报告详情

内容：

- 项目/叶片基础信息
- 检测时间
- 标记点列表
- 标记图片
- 缺陷类型、位置、方向、距离、备注
- PDF 导出

---

## 9. 录像与预览策略

Qt 当前策略需要保留到 Web：

### 非录像时

```text
相机 RTSP 主码流
  -> MediaMTX
  -> WebRTC
  -> 浏览器预览
```

### 录像时

```text
相机 RTSP 主码流
  -> 后端 Recorder 单路拉流
       -> 写 MP4 分段文件
       -> 同一路流转发给 MediaMTX
  -> WebRTC
  -> 浏览器预览
```

目标：

- 录像和预览共享同一路高清拉流。
- 避免相机被重复拉两路高清 RTSP。
- MP4 使用原始视频流复制，不重编码。
- OSD 由相机 ONVIF 写入，因此录像和抓拍天然带水印。

---

## 10. 里程碑计划

| 里程碑 | 内容 | 预估 |
|---|---|---|
| M0 骨架 | FastAPI、SQLite、Vue 平板横屏壳、MediaMTX 启停、单路 RTSP 主码流播放 | 2-3 天 |
| M1 相机闭环 | 前/后摄配置、云台/固定通道切换、ONVIF 探测、PTZ 短按/长按/停止、数字变焦 | 4-5 天 |
| M2 摄录闭环 | 单路高清录像+预览转发、拍照、存储路径、录像状态、OSD 写入 | 4-5 天 |
| M3 业务闭环 | 项目信息收集、作业会话、图片标记编辑、手动距离、报告记录 | 1 周 |
| M4 报告 | 报告中心、报告详情、PDF 导出、历史影像 | 1 周 |
| M5 后续扩展 | 小车、灯光、里程计、姿态、轨迹、雷达/双目、AI 缺陷识别 | 待排期 |

---

## 11. 部署形态

- 服务端运行在 Ubuntu 22.04。
- 后端：FastAPI + SQLite + FFmpeg + MediaMTX。
- 前端开发期使用 Vite `:5173`，生产期由 FastAPI 托管 `front_end/dist`。
- 浏览器/平板与 Ubuntu 服务端在同一局域网。
- 需要开放端口：`8000`（HTTP/API）、`8889`（MediaMTX WebRTC/WHEP）、`8554`（MediaMTX RTSP 内部/调试）。

---

## 12. 待确认问题

| # | 问题 | 当前默认方案 |
|---|---|---|
| 1 | 前后两台相机的默认 IP、账号、密码是否沿用 Qt 默认值？ | 先支持配置，不在文档写死密码。 |
| 2 | PDF 报告模板是否已有固定格式？ | 先按原型报告详情生成基础版 PDF。 |
| 3 | 平板目标分辨率 | 已确认 `2560 x 1600`，横屏优先适配。 |

---

## 附录 A：Qt 协议实现摘录

### A.1 RTSP URL

```text
rtsp://{username}:{password}@{ip}:{rtspPort}/cam/realmonitor?channel={channel}&subtype=0&unicast=true&proto=Onvif
```

### A.2 ONVIF PTZ

```text
Device service: http://{ip}:80/onvif/device_service
Media2 service: /onvif/media2_service
PTZ service:    /onvif/ptz_service
Profile token:  Profile000 优先
Action:         ContinuousMove / Stop
Velocity:       dx, -dy, 系数 0.25
```

### A.3 ONVIF OSD

```text
GetVideoSourceConfigurations
GetProfiles
GetOSDs
SetOSD
CreateOSD
DeleteOSD
```

### A.4 录像

```text
Input:      RTSP over TCP
Output:     MP4
Video:      stream copy
Audio:      dropped
Segment:    keyframe boundary
Preview:    recorder relays same stream to local preview gateway
```

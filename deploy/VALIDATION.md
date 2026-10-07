# 干净 WSL 离线部署验证

2026-10-07 在独立发行版 `PipeSight-Clean-22.04-20261007` 完成验证。使用全新 Ubuntu 22.04 amd64 根文件系统，以 `robot` 登录并通过 sudo 安装；项目实际路径为 `/home/robot/PipeSightConsoleServer`。

基础镜像来自 [Ubuntu 官方 WSL 镜像](https://cloud-images.ubuntu.com/wsl/jammy/current/)，下载文件与 [官方 SHA-256](https://cloud-images.ubuntu.com/wsl/jammy/current/SHA256SUMS) 一致：

```text
1483cc5c1dce13064f774834cbffdff226559fd522a67a381a8ea77d63fb4109
```

初始化只创建账户、启用 systemd 和复制离线包，没有联网安装软件。确认 Linux 基础环境没有 FFmpeg、Node、npm、g++、MediaMTX、Python pip/venv；未使用原发行版的虚拟环境或构建产物。

安装进程和两个应用服务位于独立网络命名空间，只有 `127.0.0.1`/`::1` 回环接口，没有外网路由。对外连接测试失败，本地服务测试成功。测试专用的网络配置只保留在验证实例中，不加入离线发行包。

## 发现并修复的问题

原离线包包含较新的 systemd 和 Python 运行时，但缺少目标机已有基础组件的配套版本。在旧版 Ubuntu 镜像上，APT 先因缺少匹配的 `systemd-sysv` 无法解析依赖；补充启动组件后，还会计划删除 `systemd-timesyncd`、`libpython3.10` 及依赖它们的软件。安装器的 `--no-remove` 阻止了删除，两次失败均未改变基础环境的包版本。

新增 `config/offline-base-packages.txt`，缓存 `systemd-sysv`、`libnss-systemd`、`libpam-systemd`、`systemd-timesyncd`、`libpython3.10` 及递归依赖。安装器按目标机需要解析这些缓存，不强制安装可选组件。离线包增加 7 个 deb，现有 348 个 deb、38 个 Python wheel，总依赖约 406 MiB；索引、依赖指纹和 SHA-256 均已更新。

## 验证结果

完整离线安装于北京时间 18:05:29 开始、18:06:35 完成，退出码为 0。APT 新安装 133 个包、升级 24 个包，未删除软件；原镜像的 562 个包全部保留为已安装状态。

| 项目 | 结果 |
| --- | --- |
| 本地 APT 安装、Python wheel 安装 | 通过；pip check 无依赖冲突 |
| npm 离线安装与生产构建 | 通过；81 个 npm 包 |
| C++ 点云桥接编译及动态库解析 | 通过 |
| 后端与桥接服务 | active、enabled，实际进程用户均为 robot |
| 健康接口、相机配置接口、前端主页 | HTTP 200 |
| 主页引用的 JavaScript、CSS | HTTP 200，内容与 MIME 类型正确 |
| FFmpeg、MediaMTX | 可用，MediaMTX 正常运行 |
| 8000/TCP、9090–9093/TCP、8189/UDP | 正常监听 |
| WSL 发行版重启后自启动 | 通过；两个服务均正常运行，重启计数为 0 |
| 部署单元测试 | 12 项通过 |
| ShellCheck | 通过 |

`deploy/systemd/` 已更新为此次验证实例生成的真实 `robot` 服务文件。目标机安装时仍按其实际目录重新生成。原 `Ubuntu-22.04` 发行版服务与健康接口检查正常。

原始安装日志、包清单、重启前后运行状态和服务日志保存在项目的 `.deploy/wsl-validation/results/`，不纳入 Git 或发行包。

未接入 USB 相机和串口设备，视频、点云数据及串口通信需要真机验证。前端构建有现有的分包告警：入口 JavaScript 约 812 kB、3D 页约 537 kB，且相机页同时静态和动态导入；构建成功，体积问题仍可作为性能优化方向。

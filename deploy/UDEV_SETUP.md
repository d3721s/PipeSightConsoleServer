# 串口 udev 绑定设置指南

把 USB 转串口设备固定成 `/dev/ttyUSB-Chassis`(底盘)和 `/dev/ttyUSB-IMU`(IMU），
无论插拔顺序或内核分配的 `ttyUSB0/1/...` 怎么变，名字都不变。

> 模板文件：`deploy/99-pipesight-serial.rules`（带占位符，需你填真实标识）。
> ⚠️ 符号链接名严格区分大小写：底盘 `ttyUSB-Chassis`、IMU `ttyUSB-IMU`，
> 必须和后端用的完全一致。

---

## 第 1 步：找出每个设备的标识

**只插一个设备**（比如先只插底盘），跑：

```bash
# 列出当前的 ttyUSB 设备
ls /dev/ttyUSB*

# 假设它是 ttyUSB0，查它的属性（vid/pid/serial/物理口）
udevadm info -a -n /dev/ttyUSB0 | grep -E 'idVendor|idProduct|serial|KERNELS=="[0-9]' | head
```

你会看到类似：
```
ATTRS{idVendor}=="1a86"
ATTRS{idProduct}=="7523"
ATTRS{serial}=="0001"            # 有的芯片有唯一序列号，有的没有/都一样
KERNELS=="1-1.2"                 # 物理 USB 口路径（topology）
```

记下这个设备的 `idVendor`、`idProduct`、`serial`、以及 `KERNELS`（第一个形如 `1-1.2` 的）。

**拔掉这个，再只插另一个设备**，重复上面，记下 IMU 的标识。

---

## 第 2 步：选匹配策略

- **策略 A（推荐，按序列号）**：如果两个适配器芯片的 `serial` **各不相同**，用
  vid+pid+serial 匹配。插哪个口都对。

- **策略 B（按物理口）**：如果两个适配器**型号相同、vid/pid/serial 都一样**
  （常见于两个一样的 CH340/CP210x），序列号没法区分，就用 `KERNELS`（物理口）
  匹配——“插在这个口上的就是底盘”。此时**设备要固定插在各自的口**。

---

## 第 3 步：填模板

编辑 `deploy/99-pipesight-serial.rules`，把占位符换成真实值，**每个设备只留一条规则**
（删掉没用的那条策略）。

**例 1：按序列号（策略 A）**
```
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", ATTRS{serial}=="CHASSIS001", SYMLINK+="ttyUSB-Chassis"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", ATTRS{serial}=="IMU0002",   SYMLINK+="ttyUSB-IMU"
```

**例 2：两个一样的芯片，按物理口（策略 B）**
```
SUBSYSTEM=="tty", KERNELS=="1-1.2", SYMLINK+="ttyUSB-Chassis"
SUBSYSTEM=="tty", KERNELS=="1-1.3", SYMLINK+="ttyUSB-IMU"
```

---

## 第 4 步：安装并生效

```bash
sudo cp deploy/99-pipesight-serial.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# 然后重新插拔两个设备，或直接重启
```

**验证**：
```bash
ls -l /dev/ttyUSB-Chassis /dev/ttyUSB-IMU
# 应看到两个软链接指向真实的 /dev/ttyUSB*
```

两个软链接都在 → 重启后端让它连上：
```bash
sudo systemctl restart pipesight-backend
curl http://127.0.0.1:8000/api/chassis/telemetry   # 看 connected / imuConnected
```

---

## 常见问题

- **软链接没出现**：多半是 vid/pid/serial 写错，或设备号查错。重做第 1 步确认。
  也可单独测一条规则是否匹配：`udevadm test $(udevadm info -q path -n /dev/ttyUSB0)`。
- **权限**：串口访问需要 `dialout` 组（`install.sh` 已把你加进去）。改完组要重新登录或重启。
- **名字要完全一致**：底盘 `ttyUSB-Chassis`、IMU `ttyUSB-IMU`，和后端
  （`server/app/config.py` 的 `chassis_serial_port` / `imu_serial_port`）必须逐字相同，
  否则后端找不到设备。
- **波特率不在 udev 管**：udev 只负责命名；底盘 38400 / IMU 9600 在 `server/.env`
  的 `PIPESIGHT_CHASSIS_BAUDRATE` / `PIPESIGHT_IMU_BAUDRATE` 配。

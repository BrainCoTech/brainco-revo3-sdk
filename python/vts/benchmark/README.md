# 视触觉传感器帧率测试

本项目包含两个用于测试摄像头 / 视触觉传感器（VTS）读取帧率的 Python 脚本。

## 脚本说明

### `scripts/read_usb_video.py`

使用 OpenCV 读取 USB 摄像头视频流，实时显示并打印帧率。

**功能特性**
- 通过 OpenCV `VideoCapture` 读取 USB 摄像头
- 默认分辨率 `320x240`，帧率 `120 FPS`，编码格式 `MJPG`
- 实时计算并打印采集帧率
- 支持通过 `--device` 指定摄像头设备 ID

**用法**

```bash
python scripts/read_usb_video.py
```

指定摄像头设备 ID：

```bash
python scripts/read_usb_video.py --device 1
```

按 `q` 或 `ESC` 退出。

---

### `scripts/vts_collect_sensor_data.py`

通过 `pyvitaisdk` 连接视触觉传感器（VTS），循环采集并打印单次数据采集耗时。

**功能特性**
- 自动查找并连接第一台可用的 VTS 设备
- 加载模型路径 `./checkpoints/BC_20260529/<sn>/<sn>.onnx.enc`
- 采集以下数据类型：
  - `WARPED_IMG`
  - `DEPTH_MAP`
  - `FORCE6D_VECTOR`
- 打印每次 `collect_sensor_data()` 的耗时（毫秒）

**用法（必须绑定 CPU 核心运行）**

RK3588共计8核，包括4个大核4个小核，其中，每个大核独立运行脚本，绑定4个小核运行脚本



```bash
taskset -c 4 python scripts/vts_collect_sensor_data.py
taskset -c 5 python scripts/vts_collect_sensor_data.py
taskset -c 6 python scripts/vts_collect_sensor_data.py
taskset -c 7 python scripts/vts_collect_sensor_data.py
```

绑定多个核心：

```bash
taskset -c 0,1,2,3 python scripts/vts_collect_sensor_data.py
```

## 目录结构

```
.
├── README.md
└── scripts/
    ├── read_usb_video.py
    └── vts_collect_sensor_data.py
```

## 注意事项

- 运行 `vts_collect_sensor_data.py` 前，请确保：
  - VTS 设备已正确连接并被系统识别；
  - `./checkpoints/BC_20260529/<sn>/<sn>.onnx.enc` 模型文件已存在；
  - 已使用 `taskset -c` 绑定到固定 CPU 核心，以获得稳定的采集时延。
- `read_usb_video.py` 为普通 USB 摄像头测试脚本，无需 `taskset` 绑定。

# BrainCo Revo3 SDK 示例

[English](README.md) | [简体中文](README.zh-CN.md)

本仓库提供使用 SDK 控制 BrainCo Revo3 灵巧手的示例应用和集成代码。

## 目录结构

- `c/`：使用 C ABI 的 C++ 示例，以及独立的 Linux EtherCAT 示例
- `python/revo3/`：Python Revo3 示例
- `python/gui/`：包含 Revo3 控制面板和 Mock 模式的 PySide GUI

安装、集成指南以及 Python 和 C/C++ API 参考见 [Revo 3 SDK 文档](https://app.brainco.cn/universal/bc-revo3-sdk/docs/site/)。硬件寄存器和运输层详细信息见 [Revo 3 通信协议](https://www.brainco-hz.com/docs/revolimb-hand/revo3/protocol.html)。

## 动作演示

Python 和 C++ 动作演示默认只做离线预览，只有传入 `--run` 才会连接硬件：

```bash
python python/revo3/gesture_dance_demo.py
./c/build/demo/gesture_dance_demo
```

动作顺序、候选姿态标定、硬件检查、中断行为以及 Python/C++ 差异见[动作演示指南](python/revo3/MOTION_DEMOS.zh-CN.md)（[English](python/revo3/MOTION_DEMOS.md)）。

## 快速开始

### C++

```bash
bash download-lib.sh
make -C c
./c/build/demo/quickstart
./c/build/demo/quickstart --move
./c/build/demo/discover_devices --scan-all
./c/build/demo/subscriptions --count 3
./c/build/demo/multi_hand
./c/build/demo/device_operations --help
./c/build/demo/firmware_update --help
./c/build/demo/touch_sensor
./c/build/demo/streaming_control --move
```

纯 C++ IgH EtherCAT 示例不使用下载的 SDK 库，因此需要单独构建。运行前请按照 `c/platform/linux/revo3_ec/README.md` 检查 IgH 主站、`/dev/EtherCAT0` 和所选网卡：

```bash
make -C c/platform/linux/revo3_ec
./c/platform/linux/revo3_ec/revo3_pdo 0
./c/platform/linux/revo3_ec/revo3_benchmark \
  --scenario motor --read full-state --duration 10
```

### Python

#### 1. 安装 SDK

首先创建并激活独立的 Python 环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

在 Windows PowerShell 中，使用 `py -3.10 -m venv .venv` 创建环境，然后运行 `.venv\Scripts\Activate.ps1` 激活环境。

从 Ali OSS 安装与本仓库版本匹配的 wheel：

```bash
bash python/install_whl.sh 2.1.0
```

#### 2. 运行示例

```bash
cd python
python -m pip install .

# Run Revo3 2.x Manager examples (requires a real Revo3 device)
python revo3/quickstart.py
python revo3/discover_devices.py --help
python revo3/subscriptions.py --help
python revo3/touch_sensor.py
python revo3/device_operations.py --help
python revo3/firmware_update.py --help
python revo3/mit_plan.py --help

# Run GUI in real-device mode (requires a connected Revo3 device)
python -m pip install '.[gui]'
python gui/main.py
```

Python `mit_plan.py` 和 C++ `mit_plan.cpp` 示例使用相同的默认五次 MIT 阻抗计划：频率为 100 Hz，目标位置为各关节配置位置范围的 50%，每个向外和返回分段用时 800 ms，`Kp=3.0`、`Kd=0.3`，前馈电流为零。可复用的 C++ 采样器位于 `c/common/revo3_mit_plan.hpp`。

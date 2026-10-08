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
bash python/install_whl.sh __VERSION__
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

Python `mit_plan.py` 和 C++ `mit_plan.cpp` 示例使用相同的默认五次 MIT 阻抗计划：频率为 100 Hz，目标位置为各关节配置位置范围的 50%，每个向外和返回分段用时 800 ms，`Kp=3.0`、`Kd=0.3`，前馈电流为零。初始位置容差默认 0.1 度；容差内的越界反馈会在运动前钳制到最近的配置限位。可复用的 C++ 采样器位于 `c/common/revo3_mit_plan.hpp`。

## 单次控制（SDK 2.1.2）

`discrete_control` 演示整手单次位置、电流及 MIT 下发，无需 `open_servo()`，
没有心跳或自动重发。需要已供电的 21 自由度 Revo3、SDK 支持的通信链路及
Linux、macOS 或 Windows 环境。2.1.2 最终 wheel 已在 UV5 固件 0.1.2 上通过
CANFD 局部控制验证。Modbus 曾通过候选实现验证；最终 wheel 的 Modbus 复测未发现设备。

默认只读取当前姿态。添加 `--run` 后，位置模式下发当前姿态，电流模式下发
零电流，MIT 模式下发当前姿态、kp=1、kd=0.1、零速度及零前馈电流。
这些命令也可能改变支撑状态或电机行为，执行前应清空工作空间。
数组按逻辑关节顺序排列，单位为度、rpm、mA；MIT 第五项是前馈电流（mA）。
目标保持由固件决定，关闭连接不会自动停止控制，应按安全 API 设计停止流程。
发生错误后先检查状态再决定是否重试，命令可能已经生效。

```bash
python python/revo3/discrete_control.py --mode mit --help
```

固件升级示例已显示传输进度。100% 表示传输完成；需重新连接并读取固件版本
确认安装成功。

2.1.2 新增 `--scope joint|finger|thumb`，选择器与 `move_*` 一致：关节 0–20、手指 1=食指到 4=小指、拇指单独使用 thumb。局部下发只写所选关节；手指/拇指逐关节写入，非原子更新，失败后先检查状态。下面命令为只读；添加 `--run` 才下发。

```bash
python python/revo3/discrete_control.py --scope joint --joint-index 0 --mode position
python python/revo3/discrete_control.py --scope finger --finger-index 1 --mode mit
./c/build/demo/discrete_control --scope thumb --mode current
```

## 设置从站 ID（SDK 2.1.2）

Python/C++ `device_operations` 新增 `--new-slave-id`，默认只读，添加 `--run` 才写入。
实际写入后需关闭旧 Manager 并新建 Manager；示例包含重新连接和身份核验。
命令与物理隔离要求见[从站 ID 示例](python/revo3/README.md#set-the-slave-id-sdk-212)。

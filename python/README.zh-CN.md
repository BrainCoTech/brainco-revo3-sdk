# BrainCo Revo3 SDK 2.x Python 示例

[English](README.md) | [简体中文](README.zh-CN.md)

所有示例均使用 2.x `Manager -> Hand` 对象 API。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./python
```

在 Windows PowerShell 中，使用 `py -3.10 -m venv .venv` 创建环境，然后运行 `.venv\Scripts\Activate.ps1` 激活环境。

安装本地 SDK 构建：

```bash
bash python/install_whl.sh
```

## 命令行

```bash
python python/revo3/quickstart.py
python python/revo3/touch_sensor.py
python python/revo3/streaming_control.py
```

完整示例列表见 `python/revo3/README.md`。

对掌、手指功能、手势舞和经典 servo 示例见[动作演示指南](revo3/MOTION_DEMOS.zh-CN.md)（[English](revo3/MOTION_DEMOS.md)）。这些示例默认只做离线预览，只有传入 `--run` 才会连接硬件。

## GUI

PySide GUI 使用相同的 2.x Manager/Hand API，不依赖旧版 `DeviceContext` 层。

```bash
python -m pip install './python[gui]'
python python/gui/main.py
```

独立的视觉触觉数据通道及其平台专用运行时不属于本 SDK 示例包。

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

`device_operations` 示例也会刷新并打印电机 SN 和版本；触觉读取失败后保留已读取的电机缓存，并报告刷新错误。

## 设置从站 ID（SDK 2.1.2）

Python/C++ `device_operations` 新增 `--new-slave-id`，默认只读，添加 `--run` 才写入。
实际写入后需关闭旧 Manager 并新建 Manager；示例包含重新连接和身份核验。
命令与物理隔离要求见[从站 ID 示例](revo3/README.md#set-the-slave-id-sdk-212)。

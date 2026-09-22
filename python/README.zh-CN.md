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

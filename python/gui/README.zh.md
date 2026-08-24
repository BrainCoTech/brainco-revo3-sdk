# BC Revo3 SDK GUI

这个 GUI 保留旧 SDK GUI 的窗口布局、Tab 组织、样式和 Revo3 面板，同时移除非 Revo3 工作流。

面板包括：

- 连接 / 自动检测
- Revo3 电机控制
- Revo3 电机配置
- Revo3 触觉
- 数据采集
- 示教模式
- DFU
- 系统配置

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './python[gui]'
```

Windows PowerShell 使用 `py -3.10 -m venv .venv` 创建环境，并运行 `.venv\Scripts\Activate.ps1` 激活。

## 运行

```bash
python python/gui/main.py
python python/gui/main.py --revo3-modbus
python python/gui/main.py --mock
python python/gui/main.py --mock revo3-mx-touch
```

`--mock` 用于 GUI 调试，不连接真实硬件。可选类型包括 `revo3`、`revo3-touch`、`revo3-mx-touch`、`revo3-pro`、`revo3-pro-touch`、`revo3-basic`、`revo3-basic-touch`。

普通 Revo3 触觉界面仅在 `hand.touch.layout` 可用时显示。SDK 无法识别底层寄存器映射时保持 fail-closed，GUI 不提供手动覆盖。

独立视触觉传感器通道、专用运行时、力模型和可视化工具不属于 Revo3 SDK 公开示例。

# BC Revo3 SDK GUI

这个 GUI 保留旧 SDK GUI 的窗口布局、Tab 组织、样式和 Revo3 面板，同时移除非 Revo3 工作流。

面板包括：

- 连接 / 自动检测
- Revo3 电机控制
- Revo3 电机配置
- Revo3 触觉
- 数据采集
- 示教模式
- 时序测试
- DFU
- 系统配置
- VisionTouch 窗口

## 安装

```bash
pip install -r examples/python/gui/requirements.txt
pip install bc-revo3-sdk
```

## 运行

```bash
python examples/python/gui/main.py
python examples/python/gui/main.py --revo3-modbus
python examples/python/gui/main.py --mock
python examples/python/gui/main.py --mock revo3-vision
```

`--mock` 用于 GUI 调试，不连接真实硬件。可选类型包括 `revo3`、`revo3-touch`、`revo3-vision`、`revo3-pro`、`revo3-pro-touch`、`revo3-basic`、`revo3-basic-touch`。

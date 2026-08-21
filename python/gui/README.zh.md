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
python python/gui/main.py --mock revo3-vision
python python/gui/main.py --mock revo3-mx-touch
python python/gui/main.py --vts-force-model-dir python/vts/checkpoints --vts-force-model-mode auto
```

`--mock` 用于 GUI 调试，不连接真实硬件。可选类型包括 `revo3`、`revo3-touch`、`revo3-mx-touch`、`revo3-vision`、`revo3-pro`、`revo3-pro-touch`、`revo3-basic`、`revo3-basic-touch`。

连接 Revo3 Ultra VisionTouch 后，主 GUI 会根据硬件类型显示 `VisionTouch` Tab。如果同一只手还上报 `mt_*` 压阻阵列或 `mx_*` 高密矩阵触觉，普通 Revo3 触觉 Tab 会同时保留。`Tools` → `VisionTouch Sensor...` 保留为跳转到 VisionTouch Tab 的快捷入口。

普通 Revo3 触觉界面仅在 `hand.touch.layout` 可用时显示。SDK 无法识别底层寄存器映射时保持 fail-closed，GUI 不提供手动覆盖。

VisionTouch 力模型加载是可选的，默认不加载以减少初始化等待：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--vts-force-model-dir` | VTS 力模型父目录：`{dir}/{SN}/{SN}.onnx.enc` | 若存在则自动使用 `python/vts/checkpoints` |
| `--vts-force-model-mode` | `none` = 快速启动不载入力模型，`auto` = 有匹配模型则加载，`required` = 缺模型则跳过对应传感器 | `none` |

只有需要 Force6D 力值时才建议使用 `--vts-force-model-mode auto`。不加载力模型时，图像、深度、Marker 等数据仍可用，初始化更快。

`VisionTouch` Tab 内也提供力模型模式选择、权重目录选择和初始化进度条。权重目录应选择包含各传感器 SN 子目录的父目录，例如 `{dir}/{SN}/{SN}.onnx.enc`。传感器已连接时修改这些设置，会在下次断开重连后生效。

真实 VTS 数据依赖 `pyvitaisdk4bc`：

```bash
bash python/install_vts_whl.sh
```

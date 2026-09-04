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
python python/gui/main.py --mock revo3-hp-ft-touch
```

`--mock` 用于 GUI 调试，不连接真实硬件。可选类型包括 `revo3`、`revo3-touch`、`revo3-mx-touch`、`revo3-hp-ft-touch`、`revo3-pro`、`revo3-pro-touch`、`revo3-basic`、`revo3-basic-touch`。

普通 Revo3 触觉界面仅在 `hand.touch.layout` 可用时显示。SDK 无法识别底层寄存器映射时保持 fail-closed，GUI 不提供手动覆盖。

对于 `hp_fingertip_ft`，GUI 显示力、力矩、合力、状态和清零控件，不显示热力图；该布局的 `point_count=0`，数据帧返回 `points=None`。仅声明了点阵数据的 `hp_*` 布局显示热力图。

## 触觉采样与绘制

GUI 将触觉采样与界面绘制分开处理。采集侧只保留最新的待绘制触觉数据；可见图表约每 `16 ms` 调度一次，界面绘制上限约为 `60 FPS`；数值标签每 `100 ms` 更新一次。隐藏面板和不可见的内部图表不处理绘制。

触觉采样请求根据触觉布局和操作系统确定：

| 触觉布局 | 平台 | 采样请求 |
|---|---|---|
| `hp_*` 力/力矩布局 | Windows 或 Linux | 使用 `5`、`20`、`30`、`60`、`90`、`120 Hz` 自适应档位，初始为 `30 Hz` |
| `hp_*` 力/力矩布局 | macOS | 最高 `5 Hz` |
| 其他触觉布局 | 所有支持的平台 | 最高 `60 Hz` |

自适应采样每 5 秒评估一次已完成的读取，并保证两次频率调整至少间隔 10 秒。实测频率达到当前目标的 90%，且评估窗口内没有新增读取错误时，GUI 提高请求频率；发生读取错误或实测频率低于目标的 70% 时，GUI 降低请求频率。

`120 Hz` 是请求上限，不是设备更新频率保证。界面显示的触觉 FPS 统计已完成的订阅数据包。如果数据包不含固件序列号或采集时间戳，GUI 无法根据连续相同的数值证明传感器产生了不同的新样本。最终频率取决于传输协议、适配器、驱动、固件、数据包大小和主机负载。

SDK 会在 Windows 和 Linux 上请求低延迟串口行为。如果 USB 串口适配器驱动提供延迟计时器设置，请先将其配置为 `1 ms`，再验证高频采样。通过触觉 FPS 指示器记录实测频率，并检查应用日志中的自适应频率变化和读取错误。

使用 Windows Modbus 连接时，GUI 根据 USB 厂商 ID `0x0403` 或串口的厂商和产品信息识别 FTDI 适配器。如果不低于 `60 Hz` 的自适应目标在评估窗口内持续低于目标的 70%，GUI 会在状态栏和应用日志中提示一次，建议检查 **设备管理器 > 端口 > 端口设置 > 高级 > Latency Timer**。GUI 不会修改驱动设置，也不会将 Latency Timer 判定为已经确认的根因；传输和设备限制可能产生相同现象。

独立视触觉传感器通道、专用运行时、力模型和可视化工具不属于 Revo3 SDK 公开示例。

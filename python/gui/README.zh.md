# BC Revo3 SDK GUI

这个 GUI 提供 Revo3 设备控制、状态监测、触觉、诊断和维护功能。

面板包括：

- 连接 / 自动检测
- Revo3 电机控制
- Revo3 电机面板中的碰撞保护测试控件
- Revo3 电机配置
- Revo3 触觉
- 数据采集
- 示教模式
- DFU
- 系统配置

## 碰撞保护测试面板

Revo3 电机面板提供用于硬件测试的碰撞保护控件。GUI 默认使用 `Hybrid`、
`SoftStop`、`debounce_time_ms=50`、`max_cached_status_age_ms=80` 和
`auto_clear_time_ms=1000`。启用运动前应检查位置误差和电流阈值；
GUI 默认值与 SDK 默认值不同。

普通拖动模式会将电机监测频率降为 10 Hz，为控制命令留出更多总线时间。
启用碰撞保护时，GUI 保持正常监测频率。按住滑块时如果收到新的固件 `Stall`
状态，GUI 会显示黄色的本地保护状态，并在松开滑块前阻止该次拖动。SDK 确认的
`collision_active` 状态显示为红色。配置和轮询在后台任务中执行，较慢的 SDK
或传输调用会写入应用日志。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './python[gui]'
```

Windows PowerShell 使用 `py -3.10 -m venv .venv` 创建环境，并运行 `.venv\Scripts\Activate.ps1` 激活。

## 运行

安装后可以从任意目录运行 `revo3-gui`。先执行 `revo3-gui --check` 检查依赖能否导入，
再用 `revo3-gui --mock` 检查界面；两者均不连接硬件。下面的脚本命令仍可从仓库根目录运行。

```bash
python python/gui/main.py
python python/gui/main.py --revo3-modbus
python python/gui/main.py --mock
python python/gui/main.py --mock ut2
python python/gui/main.py --mock uf1
```

`--mock` 用于 GUI 调试，不连接真实硬件。请使用规范三位产品代号，例如 `UB1`、`UT1`、`UT2`、`UF1`、`PB1`、`PT1`、`DB1` 或 `DT1`。

普通 Revo3 触觉界面仅在 `hand.touch.layout` 可用时显示。SDK 无法识别底层寄存器映射时保持 fail-closed，GUI 不提供手动覆盖。

对于 `fingertip_force_torque`，GUI 显示力、力矩、合力、状态和清零控件，不显示热力图；该布局的 `point_count=0`，数据帧返回 `points=None`。仅声明了点阵数据的指尖力/力矩布局显示热力图。

## 日志与诊断导出

通过 **Help > 导出诊断包...** 保存 ZIP，内容包括操作系统、Python 和依赖版本、
缓存的连接信息与设备标签、界面 FPS，以及当前会话最多三个日志文件（每个保留末尾 2 MiB）。
导出在后台执行，不发送设备命令；导出完成后才能关闭窗口。
ZIP 可能包含设备序列号、端口名和日志中的本地路径，分享前请检查内容。
不收集环境变量、固件文件或已录制的传感器数据集。

界面无法启动时，运行 `revo3-gui --diagnostics support.zip`，或
`python python/gui/main.py --diagnostics support.zip`。
该离线命令无需 GUI 依赖，只导出环境元数据。

GUI 日志默认目录：macOS 为 `~/Library/Logs/BrainCo/Revo3`，Windows 为
`%LOCALAPPDATA%/BrainCo/Revo3/logs`，Linux 为 `$XDG_STATE_HOME/brainco/revo3/logs`
（未设置时使用 `~/.local/state/brainco/revo3/logs`）。可用 `REVO3_LOG_DIR` 指定其他目录。
日志使用 UTC 时间，每个文件达到 2 MiB 时轮转，每个会话保留两份备份。
历史会话日志不会自动删除，不再需要时可自行清理。启动失败、未捕获的 Python 异常和线程异常会写入日志；
原生崩溃与操作系统强制终止不在此异常捕获范围内。

## 触觉采样与绘制

GUI 将触觉采样与界面绘制分开处理。采集侧只保留最新的待绘制触觉数据；可见图表约每 `16 ms` 调度一次，界面绘制上限约为 `60 FPS`；数值标签每 `100 ms` 更新一次。隐藏面板和不可见的内部图表不处理绘制。

触觉采样请求根据触觉布局和操作系统确定：

| 触觉布局 | 平台 | 采样请求 |
|---|---|---|
| 指尖力/力矩布局 | Windows 或 Linux | 使用 `5`、`20`、`30`、`60`、`90`、`120 Hz` 自适应档位，初始为 `30 Hz` |
| 指尖力/力矩布局 | macOS | 最高 `5 Hz` |
| 其他触觉布局 | 所有支持的平台 | 最高 `60 Hz` |

自适应采样每 5 秒评估一次已完成的读取，并保证两次频率调整至少间隔 10 秒。实测频率达到当前目标的 90%，且评估窗口内没有新增读取错误时，GUI 提高请求频率；发生读取错误或实测频率低于目标的 70% 时，GUI 降低请求频率。

`120 Hz` 是请求上限，不是设备更新频率保证。界面显示的触觉 FPS 统计已完成的订阅数据包。如果数据包不含固件序列号或采集时间戳，GUI 无法根据连续相同的数值证明传感器产生了不同的新样本。最终频率取决于传输协议、适配器、驱动、固件、数据包大小和主机负载。

SDK 会在 Windows 和 Linux 上请求低延迟串口行为。如果 USB 串口适配器驱动提供延迟计时器设置，请先将其配置为 `1 ms`，再验证高频采样。通过触觉 FPS 指示器记录实测频率，并检查应用日志中的自适应频率变化和读取错误。

使用 Windows Modbus 连接时，GUI 根据 USB 厂商 ID `0x0403` 或串口的厂商和产品信息识别 FTDI 适配器。如果不低于 `60 Hz` 的自适应目标在评估窗口内持续低于目标的 70%，GUI 会在状态栏和应用日志中提示一次，建议检查 **设备管理器 > 端口 > 端口设置 > 高级 > Latency Timer**。GUI 不会修改驱动设置，也不会将 Latency Timer 判定为已经确认的根因；传输和设备限制可能产生相同现象。

独立视触觉传感器通道、专用运行时、力模型和可视化工具不属于 Revo3 SDK 公开示例。

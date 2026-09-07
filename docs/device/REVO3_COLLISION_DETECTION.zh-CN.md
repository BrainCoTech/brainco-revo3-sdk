# Revo3 SDK 2.0 实验性碰撞与堵转保护

本文说明 Revo3 2.0 Manager/Hand API 提供的 SDK 侧实验性碰撞与堵转保护。该能力默认关闭，只能作为软件保护辅助，不属于功能安全系统，也不是经过认证的急停。检测延迟、误触发和漏检取决于传输时序、缓存状态时效、固件反馈及配置阈值。

公共 API 定义以 [Revo3 2.0 API 参考](../api/REVO3_API.zh-CN.md)为准。

## 1. 公共 API

Python 应用通过 `hand.experimental_collision` 配置和查询碰撞保护：

```python
config = sdk.ExperimentalCollisionConfig(
    enable=True,
    source=sdk.CollisionDetectionSource.HardwareOnly,
    position_error_threshold_deg=15.0,
    current_threshold_ma=800.0,
    debounce_time_ms=100,
    max_cached_status_age_ms=50,
    strategy=sdk.CollisionProtectionStrategy.SoftStop,
    auto_clear_time_ms=1000,
)
await hand.experimental_collision.configure(config)

active = await hand.experimental_collision.active_joints()
await hand.experimental_collision.reset()
```

C ABI 提供 `revo3_experimental_collision_configure`、`revo3_experimental_collision_get_active` 和 `revo3_experimental_collision_reset`。C++ 通过 `hand.experimental_collision()` 暴露同一能力域。Python 2.0 不导出 1.x `DeviceContext`、模块级碰撞函数、collector 或电机状态 buffer。

## 2. 检测来源

`source` 支持以下取值：

| 取值 | 检测输入 |
| --- | --- |
| `HardwareOnly` | 电机固件上报的 Stall 状态 |
| `SoftwareOnly` | 位置跟踪误差或反馈电流阈值 |
| `Hybrid` | 硬件 Stall 或任一软件阈值 |

软件阈值按以下方式计算：

```text
position_error = abs(planned_position - actual_position)
current = abs(actual_current)
```

SDK 只评估新收到的电机状态采样。重复使用同一缓存采样时，不会对相同的 Stall 位或阈值越界重复计数。

当 `debounce_time_ms` 大于零时，检测使用根据实测采样周期换算的有界滑动采样窗口，并要求窗口内存在多次越界采样。当前实现至少要求两次越界，最多保留 32 个采样；这些窗口细节属于实验性 API 的当前实现，后续 2.x minor 版本可能调整。值为零时，单次越界即可触发保护。实际响应时间仍取决于状态读取频率和总线延迟。

## 3. 目标运动保护

启用碰撞保护后，由 SDK 托管的 `move_to()`、`move_joint()`、`move_finger()`、`flex_finger()` 和 `move_thumb()` 目标运动循环会在发送轨迹点期间执行碰撞检查。

确认碰撞后，SDK 将：

1. 把受影响关节标记为碰撞活动状态。
2. 在有界等待时间内尝试发送配置的保护命令。
3. 停止发送被中断目标运动的后续轨迹点。
4. 通过对应的 `OperationHandle` 报告运动结果。

保护写入失败或超时会被明确报告，但不能据此确认电机已经停止。机械行为和恢复条件由固件决定，必须通过真机验证。

## 4. ServoSession 与单次命令

`ServoSession` 由调用方驱动。SDK 不会为每次 Position、Velocity、Current、Impedance 或 MIT 发送启动隐藏的 telemetry 线程，以免隐式增加总线读取并改变命令时序。

目标关节处于碰撞活动窗口时，常规控制命令会被拒绝。零增益释放命令可以继续保留，使应用能够尝试放松机械手。自行维护连续 Servo 循环的应用应按当前传输可承受的频率读取 State 和碰撞状态，并在保护生效后停止发送循环。

Servo 命令超时和碰撞检测是相互独立的事件。命令超时会将 ServoSession 置为 `Expired`，拒绝该会话继续发送并释放 SDK 软件控制权；它不会发送停止命令，也不能证明固件已经停止电机。

## 5. State 读取与内部最新采样缓存

State 订阅和碰撞检测使用同一套当前电机状态寄存器读取，因此 status、position、velocity、current 和 error 字段可以在单帧范围内比较。

2.0 的采集机制如下：

- `await hand.state.snapshot()` 发起一次当前状态读取。
- `hand.state.subscribe()` 创建拉取式订阅；每次 `await subscription.next()` 在配置的间隔后发起一次读取。
- 订阅不消费 1.x shared buffer，也不保留采样历史。

SDK 内部只保存一份最新电机状态缓存，使碰撞检测可以复用仍足够新鲜的采样，避免重复占用总线。`max_cached_status_age_ms` 限制可复用采样的最大年龄；缓存不存在或已经过期时，碰撞检测会请求新的状态。

该最新采样缓存不是队列，应用不能 pop 或 clear，也不是已经移除的公共 `Revo3MotorStatusBuffer` API。

## 6. 配置

| 字段 | 默认值 | 单位 | 含义 |
| --- | ---: | --- | --- |
| `enable` | `false` | boolean | 启用 SDK 侧碰撞保护 |
| `source` | `HardwareOnly` | enum | 选择硬件、软件或组合检测 |
| `position_error_threshold_deg` | `15.0` | degree | 软件位置误差阈值 |
| `current_threshold_ma` | `800.0` | mA | 软件反馈电流绝对值阈值 |
| `debounce_time_ms` | `100` | ms | 越界消抖窗口 |
| `max_cached_status_age_ms` | `50` | ms | 内部最新采样允许复用的最大年龄 |
| `strategy` | `SoftStop` | enum | 确认碰撞后尝试执行的保护命令 |
| `auto_clear_time_ms` | `1000` | ms | 碰撞活动状态保持时间；零表示必须显式复位 |

`strategy` 支持：

- `SoftStop`：尝试以低刚度稳定在当前反馈位置。
- `ZeroForce`：尝试在当前反馈位置发送零增益释放命令。
- `HoldActualPosition`：尝试使用当前或默认增益保持当前反馈位置。

这些名称描述 SDK 命令策略，不对应经过安全认证的停止类别。写入响应成功只能确认通信完成，不能确认完整的机械结果。

## 7. GUI 测试面板

示例 PySide GUI 在该 API 之上增加了应用级监控和显示逻辑。GUI 控件与颜色状态属于示例行为，不构成 SDK 合同。当前行为见 [GUI README](../../python/gui/README.md)。

## 8. 验证要求

发布前必须通过真机覆盖：

- 支持的 21 DOF 设备上的 HardwareOnly、SoftwareOnly 和 Hybrid 检测。
- 在实测 State/轨迹频率下的消抖行为。
- 每种保护策略及其真实电机行为。
- 写响应丢失、传输中断和缓存过期回退。
- 自动清除和显式复位。
- Modbus 与 CANFD 下 State 监控和 ServoSession 并发负载。

当前验证范围仅覆盖支持的 21 DOF 设备，不据此确认其他关节布局上的碰撞保护行为。在形成上述真机记录前，只能将该能力描述为“已实现、等待真机验证”，不得声称其能够保证停止或防止硬件损坏。

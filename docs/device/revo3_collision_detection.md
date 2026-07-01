# Revo3 SDK 碰撞与堵转保护机制说明文档

在轨迹运动（位置控制模式）下，SDK 会高频向电机下发轨迹指令。当机械手在运动过程中发生外界碰撞、遇到障碍物或发生电机堵转时，如果继续强行下发目标指令，会导致电机输出过大扭矩，从而引发关节剧烈抖动、电机发热过流，甚至造成硬件损坏。

为了解决这一问题，Revo3 SDK 引入了**碰撞与堵转保护机制**。

---

## 1. 原理与流程

在启用碰撞保护后，轨迹执行循环（频率由用户传入的 `dt` 参数决定，实际受半双工总线吞吐量限制）的流程如下：

```text
 【轨迹发包循环开始】
          │
          ▼
 【读取当前设备遥测】 ───> 发生通讯丢包？ ─── [是] ───> 忽略本次检查（使用期望缓存）
          │ [否]
          ▼
 【遍历每个活动关节】 
          │
          ├──> 硬件检测 (HardwareOnly)：检查固件返回的状态字中是否有 Stall (堵转) 标志位
          └──> 软件检测 (SoftwareOnly)：检查当前 (期望位置 - 实际位置).abs() > max_position_error 
                                     或 实际电流.abs() > max_current
          │
          ▼
 【碰撞/超限状态评估】 
          ├──> 未超限 ───> 清空该关节的消抖计时器
          └──> 超限 ─────> 是否持续超限超过 debounce_time_ms？
                            ├──> [否] ───> 启动/累加计时，正常执行本 Tick 发包
                            └──> [是] ───> 标记 collision_active 为 true，拉响碰撞警报
          │
          ▼
 【碰撞处理拦截】
          ├──> 无任何关节碰撞 ───> 正常下发本 Tick 插值指令，继续轨迹
          └──> 有关节碰撞 ───────> 1. 根据配置策略执行一次性 MIT 保护发包（如 SoftStop/ZeroForce）
                                 2. 终止并跳出整个轨迹发包循环（轨迹协程优雅自毁）
```

---

## 2. 配置选项详解

碰撞保护通过配置结构体 `CollisionProtectionConfig` 进行定义：

### 2.1 碰撞检测源 (`CollisionDetectionSource`)
* **`HardwareOnly` (0)**：仅监控电机固件返回的故障字中是否包含 `Stall` 标志位。此方式 CPU 开销最低，但灵敏度完全取决于固件底层的保护设定。
* **`SoftwareOnly` (1)**：由 SDK 软件侧实时计算位置跟踪误差与反馈电流。
* **`Hybrid` (2)**：**默认推荐值**。双路并进，任何一路触发即判定为异常。

### 2.2 保护策略 (`CollisionProtectionStrategy`)
* **`SoftStop` (0)**：**默认推荐值**。轨迹中止，将期望位置 `P_des` 固定为当前时刻的物理反馈位置 `P_actual`，并有意覆盖轨迹增益，把 MIT 控制增益 `Kp` 和 `Kd` 降级为低刚度悬停参数（`STABILIZE_KP`/`STABILIZE_KD`），使手指在碰撞处轻柔悬停，撤受力时不会反弹。
* **`ZeroForce` (1)**：轨迹中止，将期望位置固定为物理反馈位置，并将 `Kp`、`Kd` 设为 0，使手掌进入完全失力、零阻抗的顺从状态，外力可轻易拨动手指，适合安全避障与人机交互。
* **`HoldActual` (2)**：轨迹中止，将期望位置固定为物理反馈位置。当前正在执行轨迹的 active joints 会沿用被打断轨迹的当前 `Kp`/`Kd`；其他关节使用默认轨迹增益保持当前位置。

---

## 3. 多语言 API 参考

### 3.1 Python API
* 接口定义和属性绑定参考：`src/python/api/trajectory.rs`

```python
# 1. 设置配置
client.revo3_set_collision_protection_config(slave_id, config)

# 2. 获取配置
config = client.revo3_get_collision_protection_config(slave_id)

# 3. 查询碰撞活跃标志
active = client.revo3_is_collision_active(slave_id, joint_id)

# 4. 重置状态
client.revo3_reset_collision_state(slave_id)
```

### 3.2 C/C++ API
* 接口头文件参考：`dist/include/revo3-sdk.h`

```c
// 1. 设置配置
int revo3_set_collision_protection_config(DeviceHandler *handle, uint8_t slave_id, CollisionProtectionConfig config);

// 2. 获取配置
int revo3_get_collision_protection_config(DeviceHandler *handle, uint8_t slave_id, CollisionProtectionConfig *out_config);

// 3. 查询碰撞活跃标志
int revo3_is_collision_active(DeviceHandler *handle, uint8_t slave_id, uint16_t joint_id, int *out_active);

// 4. 重置状态
int revo3_reset_collision_state(DeviceHandler *handle, uint8_t slave_id);
```

---

## 4. 示例代码参考
项目内已包含完整的调试示例程序：
- **Python 示例**：`examples/python/revo3/revo3_collision_test.py`
- **C++ 示例**：`examples/c/demo/revo3_collision_test.cpp`

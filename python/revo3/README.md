# Revo3 Python API Reference

Revo3 (Revo3) 21-DoF Dexterous Hand — Motor Control & Tactile Sensor API

> SDK: `bc-revo3-sdk >= 1.3.5` · Protocol: Modbus RTU @ 5 Mbps

---

## Table of Contents

- [Protocol](#protocol)
- [Quick Start](#quick-start)
- [Connection](#connection)
- [Motor Control](#motor-control)
  - [Device Info](#device-info)
  - [Motor Status](#motor-status)
  - [Position Control](#position-control)
  - [Velocity Control](#velocity-control)
  - [Current Control](#current-control)
  - [MIT Impedance Control](#mit-impedance-control)
  - [Fingertip Cartesian Control](#fingertip-cartesian-control)
  - [Trajectory Control](#trajectory-control)
  - [Teaching Mode](#teaching-mode)
  - [Motor Settings](#motor-settings)
- [Tactile Sensor](#tactile-sensor)
  - [Module Enable/Disable](#module-enabledisable)
  - [Data Type](#data-type)
  - [Summary Data](#summary-data)
  - [Module Data](#module-data)
  - [All Touch Data](#all-touch-data)
  - [Calibrate Touch Zero](#calibrate-touch-zero)
- [DataCollector (High-Frequency)](#datacollector-high-frequency)
  - [Revo3 Basic (Motor Only)](#v3-basic-motor-only)
  - [Revo3 Full (Motor + Touch)](#v3-full-motor--touch)
  - [Dynamic Frequency Control](#dynamic-frequency-control)
  - [Buffers](#buffers)
- [Hardware Layout](#hardware-layout)
- [Examples](#examples)

---

## Protocol

- **Register map**: `RegAddrRevo3` (addresses 100+, 1000+, 2000+)
- **Joint count**: 21 joints (joint_id: 0~20, excludes 2 wrist motors)
- **Single joint control**: 3 consecutive registers (1000~1002: id + mode + param)
- **Multi-joint control**: 22 consecutive registers (1010~1031: mode + 21 params)
- **MIT control**: 6 consecutive registers (1050~1055), **atomic single write**
- **Motor feedback**: 5 separate groups (2000-2020, 2030-2050, ...), read individually
- **Additional features**: motor protection current, position/speed limits, teaching mode, touch screen switch

### API Overview

| API | Notes |
|-----|-------|
| `revo3_set_motor_position` | SingleJointId mode=0 |
| `revo3_set_motor_velocity` | SingleJointId mode=1 |
| `revo3_set_motor_current` | SingleJointId mode=2 |
| `revo3_set_motor_mit` | Atomic MIT: MitJointId 1050~1055 |
| `revo3_set_all_motor_positions` | MultiJoint mode=0, 21 joints |
| `revo3_set_all_motor_velocities` | MultiJoint mode=1, 21 joints |
| `revo3_set_all_motor_currents` | MultiJoint mode=2, 21 joints |
| `revo3_get_motor_status_data` | 5×21 register reads |
| `revo3_set_*` | Extended APIs (prefixed `revo3_`) |

Extended APIs (prefixed with `revo3_`):

| API | Description |
|-----|-------------|
| `revo3_single_joint_control(joint_id, mode, param)` | Low-level single joint |
| `revo3_multi_joint_control(mode, params[21])` | Low-level multi-joint |
| `revo3_joint_mit_control(joint_id, kp, kd, pos, vel, torque_ff)` | Atomic MIT control |
| `revo3_set_joint_mit_params(joint_id, kp, kd, pos, vel, tor)` | Set one joint in the interleaved MIT params block (1100+N×5) |
| `revo3_hand_mit_control[_without_retry](kp, kd, pos, vel, tor)` | Full-hand MIT control, interleaved by joint (1100~1204) |
| `revo3_set_all_mit_kp/kd/positions/velocities/torques(values)` | Grouped MIT single-parameter write (1300~1404) |
| `revo3_set_all_mit_params[_without_retry](kp, kd, pos, vel, tor)` | Grouped MIT all-parameter write (1300~1404) |
| `revo3_finger_control(finger_id, mode, params[4])` | Non-thumb finger control (1500~1505) |
| `revo3_thumb_control(mode, params[5])` | Thumb control (1510~1515) |
| `revo3_finger_mit_control(finger_id, params[20])` | Finger MIT (1520~1540) |
| `revo3_thumb_mit_control(params[25])` | Thumb MIT (1550~1574) |
| `revo3_set_global_protect_current(current)` | Global protection current |
| `revo3_set_joint_protect_current(joint_id, current)` | Per-joint protection |
| `revo3_set_joint_position_limits(joint_id, min, max)` | Position limits |
| `revo3_set_joint_speed_limits(joint_id, min, max)` | Speed limits |
| `revo3_set_touch_screen(enabled)` | Touch screen switch |
| `revo3_set_teaching_mode(enabled)` | Teaching mode |
| `revo3_reset_finger_defaults(finger_id)` | Restore finger defaults |
| `revo3_get_all_motor_temperatures()` | Motor temperatures [21] (°C) |
| `revo3_get_motor_temperature(motor_id)` | Single motor temperature |
| `revo3_get_motor_sn(motor_id)` | Motor serial number |
| `revo3_get_all_motor_sns()` | All motor SNs [21] |
| `revo3_get_motor_fw_versions()` | Motor firmware versions [21] |
| `revo3_get_hardware_version()` | Hardware version string |
| `revo3_get_motor_online_status()` | Motor online bitmask |

Trajectory & Teaching APIs:

| API | Description |
|-----|-------------|
| `revo3_move_joint(slave_id, joint_id, target, T, dt)` | Quintic polynomial single joint move |
| `revo3_move_joint_with_gains(slave_id, joint_id, target, T, dt, kp, kd)` | Single joint move with custom Kp/Kd |
| `revo3_move_joint_with_speed(slave_id, joint_id, target, speed, dt)` | Single joint move by speed (rpm) |
| `revo3_move_joint_with_speed_and_gains(slave_id, joint_id, target, speed, dt, kp, kd)` | Single joint move by speed with custom Kp/Kd |
| `revo3_move_hand(slave_id, targets, T, dt)` | Full hand synchronized move (21 joints) |
| `revo3_move_hand_with_gains(slave_id, targets, T, dt, kp, kd)` | Full hand move with custom Kp/Kd |
| `revo3_move_hand_with_speed(slave_id, targets, speed, dt)` | Full hand move synchronized by speed (rpm) |
| `revo3_move_hand_with_speed_and_gains(slave_id, targets, speed, dt, kp, kd)` | Full hand move by speed with custom Kp/Kd |
| `revo3_move_finger(slave_id, finger_id, targets, T, dt)` | Move non-thumb finger joints simultaneously (4 joints) |
| `revo3_move_finger_with_gains(slave_id, finger_id, targets, T, dt, kp, kd)` | Finger move with custom Kp/Kd |
| `revo3_move_thumb(slave_id, targets, T, dt)` | Move thumb joints simultaneously (5 joints) |
| `revo3_move_thumb_with_gains(slave_id, targets, T, dt, kp, kd)` | Thumb move with custom Kp/Kd |
| `revo3_teach_joint(slave_id, joint_id, dt, T)` | Record single joint (backdrive mode) |
| `revo3_teach_hand(slave_id, dt, T)` | Record full hand (backdrive mode) |
| `revo3_replay_joint(slave_id, joint_id, positions, dt, kp, kd)` | Replay recorded single joint |
| `revo3_replay_hand(slave_id, trajectory, dt, kp, kd)` | Replay recorded full hand |

---

## Quick Start

```python
import asyncio
from bc_revo3_sdk import bc_revo3_sdk as sdk

sdk.init_logging()

async def main():
    # Auto-detect Revo3 device
    (protocol, port, baudrate, slave_id) = await sdk.revo3_auto_detect_modbus()
    ctx = await sdk.modbus_open(port, baudrate)

    # Read motor status
    status = await ctx.revo3_get_motor_status_data(slave_id)
    print(f"Positions: {status.positions}")

    # Position control (motor 0 → 45°)
    await ctx.revo3_set_motor_position(slave_id, 0, 45.0)

    # Read touch summary
    summary = await ctx.revo3_get_touch_summary(slave_id)
    print(f"Touch summary: {summary}")

    sdk.modbus_close(ctx)

asyncio.run(main())
```

---

## Connection

### Auto-Detect

```python
# Auto-detect Revo3 device (scans all serial ports at 5Mbps)
(protocol_type, port_name, baudrate, slave_id) = await sdk.revo3_auto_detect_modbus()
# Returns: (str, str, int, int)
# e.g., ("modbus", "/dev/ttyUSB0", 5000000, 1)

# With specific port hint
(protocol_type, port_name, baudrate, slave_id) = await sdk.revo3_auto_detect_modbus("/dev/ttyUSB0")
```

### Manual Connection

```python
# Open Modbus connection (Revo3 default: 5Mbps)
ctx = await sdk.modbus_open("/dev/ttyUSB0", 5000000)
slave_id = 1  # default slave ID

# Close connection
sdk.modbus_close(ctx)
```

### Device Identification

```python
device_info = await ctx.revo3_get_device_info(slave_id)
# DeviceInfo fields:
#   .hardware_type   → StarkHardwareType enum
#   .sku_type        → SkuType enum
#   .serial_number   → str
#   .firmware_version → str
#   .description     → str

# Check if device supports Revo3 APIs
is_revo3 = device_info.revo3_uses_motor_api()  # → bool
```

---

## Motor Control

### Constants

| Constant        | Value | Description            |
|-----------------|-------|------------------------|
| Motor Count     | 21    | motor_id: 0 ~ 20      |
| Finger Count    | 5     | Thumb, Index, Middle, Ring, Pinky |

### Device Info

```python
fw_version  = await ctx.revo3_get_firmware_version(slave_id)   # → str
serial_num  = await ctx.revo3_get_serial_number(slave_id)       # → str
hand_type   = await ctx.revo3_get_hand_type(slave_id)           # → int/str
temperature = await ctx.revo3_get_board_temperature(slave_id)   # → float (°C)
```

### Motor Status

```python
# Read all 21 motors status in a single call
status = await ctx.revo3_get_motor_status_data(slave_id)
# Revo3MotorStatusData fields:
#   .positions   → List[float]  (21 values, degrees)
#   .velocities  → List[float]  (21 values)
#   .currents    → List[float]  (21 values, Amperes)

# Read positions only
positions = await ctx.revo3_get_all_motor_positions(slave_id)  # → List[float] (21 values)
```

### Position Control

```python
# Single motor position (degrees, float)
await ctx.revo3_set_motor_position(slave_id, motor_id, degrees)
# motor_id: 0~20
# degrees: float
#   Motor 0~18: range [-90.0, 90.0]
#   Motor 19~20 (differential): range [-105.0, 105.0]

# Example
await ctx.revo3_set_motor_position(slave_id, 0, 45.0)

# Batch: set all 21 motors at once
positions = [30.0] * 21
await ctx.revo3_set_all_motor_positions(slave_id, positions)
# positions: List[float] of exactly 21 values
```

### Velocity Control

```python
# Single motor velocity
await ctx.revo3_set_motor_velocity(slave_id, motor_id, velocity)
# motor_id: 0~22
# velocity: float, range [0.0, 1000.0]

# Example
await ctx.revo3_set_motor_velocity(slave_id, 0, 100.0)
# Stop: set velocity to 0.0
await ctx.revo3_set_motor_velocity(slave_id, 0, 0.0)
```

### Current Control

```python
# Single motor current (mA)
await ctx.revo3_set_motor_current(slave_id, motor_id, current)
# motor_id: 0~22
# current: float, range [-1024, 1024] mA

# Example
await ctx.revo3_set_motor_current(slave_id, 0, 500.0)  # 500 mA
# Stop: set current to 0.0
await ctx.revo3_set_motor_current(slave_id, 0, 0.0)
```

### MIT Impedance Control

MIT (Mini Cheetah) impedance control formula:

```
τ = Kp × (P_des - P_act) + Kd × (V_des - V_act) + T_ff
```

| Parameter | Symbol | Range              | Unit    |
|-----------|--------|--------------------|---------|
| Position  | P_des  | [-434.7, 434.7]    | degrees |
| Velocity  | V_des  | [-32767, 32767]    | rpm     |
| Current   | T_ff   | [-1024, 1024]      | mA      |
| Kp        | Kp     | [0, 10.0]          |         |
| Kd        | Kd     | [0, 10.0]          |         |

```python
# Single motor MIT control
await ctx.revo3_set_motor_mit(
    slave_id,
    motor_id,          # 0~22
    position,          # float, degrees
    velocity,          # float, rpm
    current,           # float, mA (feedforward torque)
    kp,                # float, position stiffness
    kd                 # float, velocity damping
)

# Example: Motor 0, pos=45°, vel=0, cur=500mA, Kp=5.0, Kd=0.5
await ctx.revo3_set_motor_mit(slave_id, 0, 45.0, 0.0, 500.0, 5.0, 0.5)

# Batch: all 21 joints in a single write (105 Modbus registers)
await ctx.revo3_set_all_mit_params(
    slave_id,
    kp_values,         # List[float], 21 values
    kd_values,         # List[float], 21 values
    positions,         # List[float], 21 values
    velocities,        # List[float], 21 values
    torques            # List[float], 21 values
)

# Batch: set Kp/Kd only
await ctx.revo3_set_all_mit_kp(slave_id, kp_values)
await ctx.revo3_set_all_mit_kd(slave_id, kd_values)
```

### Fingertip Cartesian Control

Fingertip Cartesian control is not exported in the current Python API.
Use joint-level Revo3 APIs (`revo3_finger_control`, `revo3_thumb_control`,
`revo3_finger_mit_control`, `revo3_thumb_mit_control`) for now.

### Motor Settings

```python
# Calibration
await ctx.revo3_set_calibration_current(slave_id, current)  # float, mA
await ctx.revo3_set_auto_calibration(slave_id, enabled)      # bool

# Zero-position setup changes persistent calibration. Use only when the hand
# is in the intended reference pose.
# 1. Set explicit zero offsets (accepts list up to 21 values, e.g. 13, 16, or 21)
await ctx.revo3_set_zero_position(slave_id, offsets_deg)

# 2. Set current position as zero (recommended workflow: disable -> pose -> enable -> set)
# Step 1: Disable motors
# Step 2: Manually pose hand to zero-reference
# Step 3: Enable motors
await ctx.revo3_set_current_position_as_zero(slave_id)

# Motion limits
await ctx.revo3_set_global_protect_current(slave_id, current) # float, mA

# Error handling
await ctx.revo3_clear_motor_errors(slave_id)

# Protection & configuration
await ctx.revo3_set_global_protect_current(slave_id, current)      # float, mA
await ctx.revo3_set_joint_protect_current(slave_id, joint_id, cur) # joint 0~20, mA
await ctx.revo3_set_joint_position_limits(slave_id, joint_id, min_raw, max_raw)
await ctx.revo3_set_joint_speed_limits(slave_id, joint_id, min_raw, max_raw)
await ctx.revo3_set_touch_screen(slave_id, enabled)                # bool
await ctx.revo3_set_teaching_mode(slave_id, enabled)               # bool
await ctx.revo3_reset_finger_defaults(slave_id, finger_id)         # restore defaults

# Motor diagnostics
temps = await ctx.revo3_get_all_motor_temperatures(slave_id)       # List[int], °C
temp = await ctx.revo3_get_motor_temperature(slave_id, motor_id)   # int, °C
sn = await ctx.revo3_get_motor_sn(slave_id, motor_id)              # str
hw_ver = await ctx.revo3_get_hardware_version(slave_id)            # str
online = await ctx.revo3_get_motor_online_status(slave_id)         # int (bitmask)
```

### Trajectory Control

Host-side quintic polynomial trajectory planning. Generates smooth motion
with zero velocity/acceleration at start and end.

> **Speed unit:** All speed/velocity parameters use **RPM** (`1 RPM = 6 °/s`).

```python
# Single joint: move J3 (Pinky DIP) to 45° over 2 seconds
await ctx.revo3_move_joint(slave_id, joint_id=3, target=45.0, duration=2.0, dt=0.01)

# Single joint by speed: move J3 to 45° at 30 rpm
await ctx.revo3_move_joint_with_speed(slave_id, joint_id=3, target=45.0, speed=30.0, dt=0.01)

# Single joint with custom stiffness/damping
await ctx.revo3_move_joint_with_gains(
    slave_id, joint_id=1, target=60.0,
    duration=1.5, dt=0.01, kp=5.0, kd=0.5
)

# Full hand: move all 21 joints simultaneously
targets = [0.0] * 21
targets[1] = 45.0   # Pinky MCP
targets[5] = 45.0   # Ring MCP
targets[9] = 45.0   # Middle MCP
targets[13] = 45.0  # Index MCP
targets[17] = 45.0  # Thumb MCP
await ctx.revo3_move_hand(slave_id, targets, duration=3.0, dt=0.01)

# Full hand by uniform speed: 20 rpm
await ctx.revo3_move_hand_with_speed(slave_id, targets, speed=20.0, dt=0.01)

# With custom gains
await ctx.revo3_move_hand_with_gains(
    slave_id, targets, duration=3.0, dt=0.01, kp=5.0, kd=0.5
)

# Move non-thumb finger: move Index (finger_id=1) MCP & PIP joints to 45° over 2 seconds
await ctx.revo3_move_finger(slave_id, finger_id=1, target_positions=[0.0, 45.0, 45.0, 0.0], duration=2.0, dt=0.01)

# Move thumb: move CMC Flex & CMC Abd to 30° over 2 seconds
await ctx.revo3_move_thumb(slave_id, target_positions=[30.0, 30.0, 0.0, 0.0, 0.0], duration=2.0, dt=0.01)
```

### Teaching Mode

Backdrive recording: joints become compliant (zero torque), positions are
sampled at `dt` interval for `T` seconds, then replayed with MIT control.

```python
# Record single joint for 5 seconds at 50Hz
recorded = await ctx.revo3_teach_joint(slave_id, joint_id=3, dt=0.02, duration=5.0)
# → List[float], e.g. 250 position samples

# Replay the recorded trajectory
await ctx.revo3_replay_joint(slave_id, joint_id=3, positions=recorded, dt=0.02, kp=3.0, kd=0.3)

# Full hand record + replay
trajectory = await ctx.revo3_teach_hand(slave_id, dt=0.02, duration=5.0)
# → List[List[float]], e.g. 250 frames × 21 joints

await ctx.revo3_replay_hand(slave_id, trajectory=trajectory, dt=0.02, kp=3.0, kd=0.3)
```

---

## Tactile Sensor

### Overview

Revo3 has 11 touch modules (416 total sampling points:

| Module ID | Name       | Points | Description        |
|-----------|------------|--------|--------------------|
| 0         | Palm       | 36     | Palm pad           |
| 1         | ThumbTip   | 31     | Thumb fingertip    |
| 2         | ThumbPad   | 57     | Thumb pad          |
| 3         | IndexTip   | 21     | Index fingertip    |
| 4         | IndexPad   | 52     | Index pad          |
| 5         | MiddleTip  | 21     | Middle fingertip   |
| 6         | MiddlePad  | 52     | Middle pad         |
| 7         | RingTip    | 21     | Ring fingertip     |
| 8         | RingPad    | 52     | Ring pad           |
| 9         | PinkyTip   | 21     | Pinky fingertip    |
| 10        | PinkyPad   | 52     | Pinky pad          |

Summary register provides 42 aggregated values (indices 0~41) mapping to the complete 42 zones of the Revo3 hand (Palm, Thumb, and 4 non-thumb fingers' tip/middle/lower pad sub-segments):

| Finger | Zones Range | Segment Description |
|--------|:-----------:|---------------------|
| **Palm** | `0` | Palm Aggregate Force |
| **Thumb** | `1 ~ 9` | Tip / Upper Pad / Lower Pad subdivisions |
| **Index** | `10 ~ 17` | Tip / Upper Pad / Lower Pad subdivisions |
| **Middle**| `18 ~ 25` | Tip / Upper Pad / Lower Pad subdivisions |
| **Ring** | `26 ~ 33` | Tip / Upper Pad / Lower Pad subdivisions |
| **Pinky** | `34 ~ 41` | Tip / Upper Pad / Lower Pad subdivisions |

### Module Enable/Disable

```python
# Enable all 11 modules (bitmask: bits 0~10)
all_bits = 0x7FF  # 0b111_1111_1111
await ctx.revo3_set_all_touch_modules_enabled(slave_id, all_bits)

# Read enabled modules
enabled_bits = await ctx.revo3_get_all_touch_modules_enabled(slave_id)
# → int (bitmask), bit i = module i enabled

# Enable/disable single module
await ctx.revo3_set_touch_module_enabled(slave_id, module_id, enabled)
# module_id: 0~10
# enabled: bool

# Read single module enabled state
is_enabled = await ctx.revo3_get_touch_module_enabled(slave_id, module_id)
# → bool
```

### Data Type

```python
# Set data output type
await ctx.revo3_set_touch_data_type(slave_id, data_type)
# data_type: 0 = Pressure Array, 1 = Force Summary

# Read current data type
data_type = await ctx.revo3_get_touch_data_type(slave_id)
# → int (0 or 1)
```

### Summary Data

```python
# Read summary force values (42 aggregated pad values)
summary = await ctx.revo3_get_touch_summary(slave_id)
# → List[int] (42 values, in mN)
# Layout: [palm, thumb, index, middle, ring, pinky zones]
```

### Module Data

```python
# Read single module pressure array
data = await ctx.revo3_get_touch_module_data(slave_id, module_id)
# module_id: 0~10
# → List[int] (variable length per module, see table above)

# Example: read palm (29 points)
palm_data = await ctx.revo3_get_touch_module_data(slave_id, 0)
print(f"Palm: {len(palm_data)} points, total={sum(palm_data)}")
```

### All Touch Data

```python
# Read all data at once (summary + all 11 module arrays)
touch_data = await ctx.revo3_get_all_touch_data(slave_id)
# Revo3TouchData fields:
#   .summary  → List[int] (42 values)
#   .modules  → List[List[int]] (11 modules, each with variable points)

# Revo3TouchData is also returned by Revo3TouchDataBuffer (DataCollector)
```

### Calibrate Touch Zero

```python
# Calibrate zero drift for a single module
await ctx.revo3_calibrate_touch_zero_single(slave_id, module_id)  # module_id: 0~10

# Calibrate zero drift for all modules
await ctx.revo3_calibrate_touch_zero(slave_id)
```

---

## DataCollector (High-Frequency)

For real-time monitoring, use `DataCollector` which runs a background thread polling motor/touch data into lock-free ring buffers.

### Revo3 Basic (Motor Only)

```python
# Create buffer
motor_buffer = sdk.Revo3MotorStatusBuffer(max_size=1000)

# Create and start collector
collector = sdk.DataCollector.new_revo3_basic(
    ctx=ctx,                       # DeviceContext
    motor_buffer=motor_buffer,     # Revo3MotorStatusBuffer
    slave_id=slave_id,             # int
    motor_frequency=200,           # Hz (macOS: 200, Linux: 2000)
    enable_stats=False             # bool, print stats to console
)
collector.start()

# Read data (non-blocking)
latest = motor_buffer.peek_latest()  # → Revo3MotorStatusData or None
if latest:
    print(f"Position[0]: {latest.positions[0]}")

all_data = motor_buffer.pop_all()    # → List[Revo3MotorStatusData], clears buffer

# Stop
collector.stop()
collector.wait()  # Wait for background thread to finish
```

### Revo3 Full (Motor + Touch)

```python
# Create buffers
motor_buffer = sdk.Revo3MotorStatusBuffer(max_size=1000)
touch_buffer = sdk.Revo3TouchDataBuffer(max_size=100)

# Create collector with both motor and touch
collector = sdk.DataCollector.new_revo3_full(
    ctx=ctx,
    motor_buffer=motor_buffer,
    touch_buffer=touch_buffer,
    slave_id=slave_id,
    motor_frequency=200,           # Hz (motor polling rate)
    touch_frequency=5,             # Hz (touch is heavy: ~180ms per read)
    enable_stats=False
)
collector.start()

# Read touch data
touch_list = touch_buffer.pop_all()  # → List[Revo3TouchData]
for td in touch_list:
    print(f"Summary: {td.summary}")   # 42 values
    print(f"Modules: {len(td.modules)}")  # 11 modules
```

### Dynamic Frequency Control

```python
# Update frequencies at runtime (thread-safe, uses atomic variables)
collector.update_motor_frequency(0)     # Disable motor collection
collector.update_touch_frequency(20)    # 20Hz touch

collector.update_motor_frequency(200)   # Re-enable motor at 200Hz
collector.update_touch_frequency(0)     # Disable touch collection
```

### Buffers

| Buffer Class            | Item Type            | Methods                                              |
|-------------------------|----------------------|------------------------------------------------------|
| `Revo3MotorStatusBuffer`   | `Revo3MotorStatusData`  | `peek_latest()`, `pop_all()`, `clear()`, `len()`     |
| `Revo3TouchDataBuffer`     | `Revo3TouchData`        | `peek_latest()`, `pop_all()`, `clear()`, `len()`     |

**Revo3MotorStatusData** fields:
- `.positions` → `List[float]` (21 values, degrees)
- `.velocities` → `List[float]` (21 values)
- `.currents` → `List[float]` (21 values, mA)

**Revo3TouchData** fields:
- `.summary` → `List[int]` (42 values, mN)
- `.modules` → `List[List[int]]` (11 modules)

---

## Hardware Layout

> 📄 Complete joint anatomy, motor photos, and spec diagrams: [revo3_joint_map.md](revo3_joint_map.md)

### Motor → Finger Mapping

```
Finger    Motor IDs (top-to-bottom)        DoF
────────  ──────────────────────────────    ───
Thumb     M18(IP), M17(MCP), M16(CMC-Rot)   3   + M19, M20 (differential)
Index     M15(DIP), M14(PIP), M13(MCP), M12(Abd)   4
Middle    M11(DIP), M10(PIP), M09(MCP), M08(Abd)   4
Ring      M07(DIP), M06(PIP), M05(MCP), M04(Abd)   4
Pinky     M03(DIP), M02(PIP), M01(MCP), M00(Abd)   4
                                           ──
                                     Total: 21 motors, 21 DoF
```

### Position Ranges

| Motor ID | Finger | Joint | Range |
|----------|--------|-------|-------|
| M0 | Pinky | Abd | -14° ~ 15° |
| M1~M3 | Pinky | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M4 | Ring | Abd | ±15° |
| M5~M7 | Ring | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M8 | Middle | Abd | ±15° |
| M9~M11 | Middle | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M12 | Index | Abd | ±15° |
| M13~M15 | Index | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M16 | Thumb | CMC Rotation | -30° ~ 90° |
| M17 | Thumb | MCP | -10° ~ 90° |
| M18 | Thumb | IP | -10° ~ 103° |
| M19 | Thumb | CMC Abd (diff) | 0° ~ 110° |
| M20 | Thumb | CMC Flex (diff) | 0° ~ 75° |

### Touch Module Layout

```
Module  Name        Pts    Location
──────  ──────────  ─────  ──────────────
 0      Palm         36    Palm center
 1      ThumbTip     31    Thumb fingertip
 2      ThumbPad     57    Thumb pad
 3      IndexTip     21    Index fingertip
 4      IndexPad     52    Index pad
 5      MiddleTip    21    Middle fingertip
 6      MiddlePad    52    Middle pad
 7      RingTip      21    Ring fingertip
 8      RingPad      52    Ring pad
 9      PinkyTip     21    Pinky fingertip
10      PinkyPad     52    Pinky pad
                    ─────
            Total:   416   sampling points
```

---

## Examples

| Script                    | Description                            |
|---------------------------|----------------------------------------|
| `revo3/revo3_motor.py`    | Motor control demo (position, current, MIT) |
| `revo3/revo3_trajectory.py` | Trajectory control & teaching mode demo |
| `revo3/revo3_teaching.py` | Interactive teaching: record & playback hand movements |
| `revo3/revo3_dfu.py`      | Firmware upgrade (OTA via Modbus) |
| `revo3/revo3_timing_test.py` | Single motor timing test w/ DataCollector |
| `revo3/revo3_servo.py`    | High-frequency (100Hz) real-time servo control |
| `revo3/auto_detect.py` | Revo3 auto-detection |
| `revo3/hand_demo.py` | Revo3 hand-level info/status/touch/movement demo |
| `revo3/hand_trajectory.py` | Revo3 hand-level trajectory demo |
| `revo3/hand_dfu.py` | Revo3 firmware upgrade |
| `revo3/mit_debug/trajectory_to_c.py` | Convert trajectory JSON → C header for firmware debug |
| `revo3/jitter_analysis.py` | Analyze trajectory jitter metrics, A/B comparison |
| `revo3/mit_debug/quintic_trajectory.h` | C header: quintic interpolator for firmware MIT tracking |
| `demo/hand_touch_revo3.py`   | Tactile sensor full demo               |

### Run Examples

```bash
# Motor control
python revo3/revo3_motor.py
python revo3/revo3_motor.py --port /dev/ttyUSB0

# High-frequency Real-time Servo control (100Hz)
python revo3/revo3_servo.py
python revo3/revo3_servo.py --port /dev/ttyUSB0

# Timing test (M3, 5 cycles)
python revo3/revo3_timing_test.py
python revo3/revo3_timing_test.py --motor 5 --cycles 10 --angle 60.0

# Teaching mode (record hand movements, then replay)
python revo3/revo3_teaching.py                                    # Interactive record + playback
python revo3/revo3_teaching.py --save pen_spin.json               # Record and save trajectory
python revo3/revo3_teaching.py --load pen_spin.json --loop 5      # Load and loop playback
python revo3/revo3_teaching.py --speed 0.5                        # Half-speed playback
python revo3/revo3_teaching.py --freq 50                          # Record at 50Hz

# Convert trajectory to C header (for firmware-side playback debug)
python revo3/mit_debug/trajectory_to_c.py trajectory.json                   # Generate trajectory_data.h
python revo3/mit_debug/trajectory_to_c.py trajectory.json --freq 200         # Resample to 200Hz
python revo3/mit_debug/trajectory_to_c.py trajectory.json -o my_traj.h       # Custom output path

# Analyze jitter from recorded trajectory
python revo3/jitter_analysis.py trajectory.json                    # Per-motor jitter report
python revo3/jitter_analysis.py trajectory.json --plot             # With visualization
python revo3/jitter_analysis.py baseline.json optimized.json       # A/B comparison

# Firmware C header — quintic trajectory interpolator
# Copy revo3/mit_debug/quintic_trajectory.h into firmware project, then:
#   #include "quintic_trajectory.h"
#   QuinticTraj traj;
#   quintic_init(&traj, 0.0f, 80.0f, 2.0f);   // 0°→80° in 2s
#   quintic_get(&traj, t, &pos, &vel);         // call in 200Hz loop

# Tactile sensor
python demo/hand_touch_revo3.py
python demo/hand_touch_revo3.py -m /dev/ttyUSB0 5000000 1

# GUI (Revo3 Modbus)
python gui/main.py --revo3-modbus
```

---

## Deprecated & Removed Features

| Feature | Notes |
|---------|-------|
| LED Switch (register 104) | `set_led_enabled()` removed |
| MaxAcceleration (register 115) | `revo3_set_max_acceleration()` removed |

## Motor Status Bitmask

Each motor status/error is a `u16` bitmask:

| Bit | Flag | Condition | Recovery |
|:---:|------|-----------|----------|
| 0 | OverCurrent | Sustained ≥1.5A for 50ms | Auto-stop |
| 1 | OverVoltage | >26V | Reduce supply |
| 2 | UnderVoltage | <8V | Charge battery |
| 3 | OverTemperature | >110°C | Recovers <90°C |
| 4 | CurrentSpike | Peak 2A | Auto-stop |
| 8 | Stalled | Motor blocked | Check obstruction |
| 11 | Running | Motor active | Status, not error |

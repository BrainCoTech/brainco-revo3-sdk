# Revo3 Motor API Reference

21 DoF Dexterous Hand with 21 Motors

> **Note:** All APIs use the Revo3 protocol with **joint-based** addressing (21 joints).
> All speed/velocity parameters use **RPM** (`1 RPM = 6 °/s`).

## Table of Contents
1. [Control Modes](#control-modes)
2. [Single / Multi Joint Control](#single--multi-joint-control)
3. [MIT Control (Impedance / Force-Position Hybrid)](#mit-control-impedance--force-position-hybrid)
4. [High-Frequency Real-Time Servo Control (Servo APIs)](#high-frequency-real-time-servo-control-servo-apis)
5. [High-Level Motion Control (Trajectory & Teaching)](#high-level-motion-control-trajectory--teaching)
6. [Status Read](#status-read)
7. [System Info](#system-info)
8. [Calibration & Config](#calibration--config)
9. [Motor Status Code (Bitmask)](#motor-status-code-bitmask)
10. [Register Map](#register-map)

## Control Modes

| Value | Mode | Parameter | Description |
|:-----:|------|-----------|-------------|
| 0 | Position | Target angle (deg) | Pure position control |
| 1 | Speed | Target velocity (rpm) | Pure velocity control |
| 2 | Current | Target current (mA) | Pure torque/current control |
| 4 | Impedance | Impedance coefficient (Kp) | Position stiffness — simplified MIT |
| 5 | Damping | Damping coefficient (Kd) | Velocity damping — simplified MIT |

### Data Conversion Rules

> **Important SDK Note:** The Revo3 SDK handles all `x100` encoding/decoding automatically. You should **always pass direct physical float values** (`f32` in Rust/C++, `float` in Python) to the SDK APIs (e.g., passing `150.5` degrees, `50.0` RPM). The table below documents the internal Modbus/CAN protocol encoding, not the SDK API interface.

| Parameter | Conversion | Register Type |
|-----------|-----------|---------------|
| Position, Velocity | `value × 100` → i16 | X100 scaling |
| Kp, Kd | `value × 100` → u16 | X100 scaling |
| Current / Torque | Direct mA → i16 | No scaling |
| Temperature | Direct °C → u16 | No scaling |

## Single / Multi Joint Control

| API | Description | Registers |
|-----|-------------|-----------|
| `revo3_single_joint_control(slave_id, joint_id, mode, param)` | Single joint control | 1000~1002 |
| `revo3_multi_joint_control(slave_id, mode, params[21])` | Multi-joint synchronous control | 1010~1031 |

## MIT Control (Impedance / Force-Position Hybrid)

```
τ = Kp * (pos_ref − pos_actual) + Kd * (vel_ref − vel_actual) + τ_ff
```

| Term | Symbol | Meaning | Typical Range |
|------|--------|---------|---------------|
| Position stiffness | `Kp` | Spring-like force toward target position | 0.0 ~ 10.0 |
| Velocity damping | `Kd` | Damper-like resistance to speed deviation | 0.0 ~ 10.0 |
| Target position | `pos_ref` | Desired angle | ±434.7° |
| Target velocity | `vel_ref` | Desired angular velocity | ±32767 rpm |
| Feedforward torque | `τ_ff` | Direct force (gravity compensation, etc.) | ±1024 mA |

**Relationship to Control Modes:**
- Mode 4 (Impedance) ≈ MIT with only Kp active
- Mode 5 (Damping) ≈ MIT with only Kd active
- Full MIT = complete Kp + Kd + pos_ref + vel_ref + τ_ff control

> **Understanding `τ_ff` (Feedforward Torque):**
> In advanced robotics (e.g., quadruped legs, robotic arms), `τ_ff` is used for **Gravity Compensation** (outputting a constant force against gravity so the joint feels "weightless" while maintaining 0 positional error) and **Dynamic/Inertial Feedforward** (providing pre-calculated F=m*a force to eliminate phase lag during high-speed trajectory tracking).
> 
> **For the Revo3 Dexterous Hand:** Given the extremely light mass of the finger linkages and the transmission characteristics, complex dynamic heavy-lifting or gravity compensation is rarely required. Consequently, `τ_ff` is typically maintained at `0`, and the control relies on the `Kp` and `Kd` error-driven terms to provide a compliant, elastic impedance response.

| API | Description | Registers |
|-----|-------------|-----------|
| `revo3_joint_mit_control(slave_id, joint_id, kp, kd, pos, vel, torque)` | Single joint MIT | 1050~1055 |
| `revo3_set_joint_mit_params(slave_id, joint_id, kp, kd, pos, vel, torque)` | Set one joint in the interleaved MIT params block | 1100+N×5 |
| `revo3_hand_mit_control(slave_id, kp[21], kd[21], pos[21], vel[21], tor[21])` | Full-hand MIT control, interleaved by joint | 1100~1204 (105) |

### Grouped MIT Parameter Control

| API | Description | Registers |
|-----|-------------|-----------|
| `revo3_set_all_mit_kp(slave_id, kp[21])` | Grouped Kp params | 1300~1320 |
| `revo3_set_all_mit_kd(slave_id, kd[21])` | Grouped Kd params | 1321~1341 |
| `revo3_set_all_mit_positions(slave_id, pos[21])` | Grouped position params | 1342~1362 |
| `revo3_set_all_mit_velocities(slave_id, vel[21])` | Grouped velocity params | 1363~1383 |
| `revo3_set_all_mit_torques(slave_id, tor[21])` | Grouped torque params (mA) | 1384~1404 |
| `revo3_set_all_mit_params(slave_id, kp, kd, pos, vel, tor)` | All 5 params grouped | 1300~1404 (105) |

> **Interleaved hand control (1100~1204) vs grouped params (1300~1404):**
> - `revo3_hand_mit_control`: data **interleaved** per joint — `[j0_kp, j0_kd, j0_pos, j0_vel, j0_tor, j1_kp, ...]`
> - `revo3_set_all_mit_params`: data **grouped** by parameter — `[kp×21, kd×21, pos×21, vel×21, tor×21]`
> 
> **Note on High-Frequency Control (`without_retry`):**
> By default, the SDK uses robust write commands that automatically retry on timeout/failure. 
> For **real-time control loops** (e.g. trajectories, teleoperation, VR mapping) where blocking on a dropped packet causes jitter, you should use the `_without_retry` variants: 
> `revo3_hand_mit_control_without_retry` and `revo3_set_all_mit_params_without_retry`.

### Finger-Level Control

| API | Description | Registers |
|-----|-------------|-----------|
| `revo3_finger_control(slave_id, finger_id, mode, params[4])` | Non-thumb finger (4 joints: Abd, MCP, PIP, DIP) | 1500~1505 |
| `revo3_thumb_control(slave_id, mode, params[5])` | Thumb (5 joints: CMC_flex, CMC_abd, MCP, IP, DIP) | 1510~1515 |
| `revo3_finger_mit_control(slave_id, finger_id, params[20])` | Finger MIT (4 joints × 5 params) | 1520~1540 |
| `revo3_thumb_mit_control(slave_id, params[25])` | Thumb MIT (5 joints × 5 params) | 1550~1574 |

**finger_id**: 1=Index, 2=Middle, 3=Ring, 4=Pinky (NOT 0-based for non-thumb)

### Protection & Configuration

| API | Description | Registers |
|-----|-------------|-----------|
| `revo3_set_global_protect_current(slave_id, mA)` | Global protection current | 200 |
| `revo3_set_joint_protect_current(slave_id, joint_id, mA)` | Per-joint protection current | 201~221 |
| `revo3_set_joint_position_limits(slave_id, joint_id, min, max)` | Joint position limits | 240~290 |
| `revo3_set_joint_speed_limits(slave_id, joint_id, min, max)` | Joint speed limits | 300~341 |
| `revo3_reset_finger_defaults(slave_id, finger_id)` | Reset finger to factory defaults | — |

---

## High-Frequency Real-Time Servo Control (Servo APIs)

For high-frequency, real-time closed-loop control applications (e.g., 100Hz - 500Hz haptic teleoperation, VR glove mapping, or compliance controllers), conventional trajectory planning and standard blocking Modbus commands cause command starvation and mechanical jitter.

The SDK introduces a dedicated **Servo Control Suite** that features:
- **Zero-Retry, Single-Write Architecture:** Executes single Modbus/CANFD writes and returns immediately without blocking thread progression or retrying.
- **Built-in First-Order Low-Pass Filter (LPF):** Automatically filters incoming high-frequency positional commands locally on the host to ensure smooth mechanical transitions and reduce current spikes.
- **Second-Order Critically Damped System Simulator:** Numerical physics simulation of a mass-spring-damper system, guaranteeing both position and velocity continuity with absolutely zero overshoot even under step targets.
- **Auto Filter State Warm-Up:** Automatically warms the filter's history cache using current actual joint positions upon receiving the first command to prevent severe zero-drop jumps.

### Servo APIs

| API | Description | Typical Application |
|-----|-------------|---------------------|
| `revo3_set_servo_lpf_alpha(alpha)` | Sets first-order LPF factor alpha in (0.0, 1.0]. Default is `1.0` (filtering disabled). | Set to e.g. `0.2` to smooth jagged input trajectories (deprecated for mode-based API). |
| `revo3_get_servo_lpf_alpha()` | Gets current LPF alpha factor. | Debugging current smoothing. |
| `revo3_set_servo_filter_mode(mode)` | Sets servo smoothing filter mode: `0` = None, `1` = FirstOrderLpf, `2` = SecondOrderCriticallyDamped. Default is `0`. | Select `2` for advanced physics-based smooth tracking. |
| `revo3_get_servo_filter_mode()` | Gets current servo filter mode. | Verification of active filter configurations. |
| `revo3_set_servo_damping_omega(omega)` | Sets second-order filter natural frequency $\omega_n$ (rad/s). Higher values mean faster tracking but less smoothing. Default is `20.0`. | Tune for physical responsiveness. |
| `revo3_get_servo_damping_omega()` | Gets current natural frequency $\omega_n$. | Debugging damping parameters. |
| `revo3_servo_joint(slave_id, joint_id, pos, vel)` | Servos single joint using default gains (Kp=2.25, Kd=0.35). | Single finger real-time mapping. |
| `revo3_servo_joint_with_gains(..., kp, kd)` | Servos single joint using custom gains. | Interactive compliance tuning. |
| `revo3_servo_hand(slave_id, positions[21], velocities[21])` | Servos all 21 joints simultaneously using default gains (Kp=2.25, Kd=0.35). | Full-hand VR glove tracking. |
| `revo3_servo_hand_with_gains(..., kp, kd)` | Servos all 21 joints simultaneously using custom gains. | Dynamic impedance/admittance loops. |

## High-Level Motion Control (Trajectory & Teaching)

The SDK provides high-level motion primitives that perform smooth trajectory interpolation and manual guidance (drag-teaching) on the host side. These APIs do not directly map to single hardware registers but internally manage high-frequency control loops using the underlying MIT protocol.

### Why High-Level Motion Control is Optimized for Low-Frequency / Non-Real-Time Decision Loops

In practical robotic tasks (e.g., high-level RL policy planning, vision-guided grasping, or state-machine behavior execution), the user's decision-making loop typically runs at a **low frequency (e.g., 10Hz to 30Hz)** or is event-driven (single point-to-point command trigger). Directly streaming raw positional targets to the hand at low rates creates massive mechanical steps and joint jitter.

The High-Level Motion Control suite perfectly addresses this by decoupling the **low-frequency user decision loop** from the **high-frequency motor control loop**:

```mermaid
graph TD
    User["User Low-Frequency Policy Loop (10Hz - 30Hz) <br> e.g., move_hand(target, duration=0.8s)"]
    SDK["SDK Trajectory Solver (Quintic Blending) <br> Decouples & Computes C2 Continuous Curve"]
    MIT["Interleaved / Grouped MIT Protocol Writes <br> to Dexterous Hand Hardware"]

    User -->|Asynchronous Interrupt / Target Update| SDK
    SDK -->|High-Frequency Loop 100Hz - 500Hz, dt=2ms - 10ms| MIT
```

| Dimension | High-Frequency Real-Time Servo (Servo APIs) | High-Level Motion Control (Trajectory APIs) |
| :--- | :--- | :--- |
| **Control Frequency** | High-frequency streaming (**100Hz - 500Hz**) | Low-frequency / non-real-time (**10Hz - 30Hz** or event-driven) |
| **Decoupling Layer** | None. User must manually handle trajectory smoothing. | Fully managed by the SDK host-side runner thread. |
| **Command Interruption** | Step targets cause physical shocks unless filtered by LPF/Second-order model. | Smoothly resolved mid-course via dynamic **Quintic Blending**. |
| **Typical Use Cases** | Haptic teleoperation, VR glove tracking, real-time closed-loop admittance. | Vision-based grasping pipelines, pick-and-place, sequence-based tasks. |

### Trajectory Control (Quintic Polynomial & Quintic Blending)

Moves joints smoothly over a specified duration with automatic support for **Quintic Blending**. Under the hood, the trajectory solver calculates a 5th-order polynomial trajectory supporting arbitrary non-zero initial boundary conditions (initial velocity $v_0$ and initial acceleration $a_0$) and smoothly decelerates to zero velocity and acceleration at the target. This ensures perfectly smooth transitions during dynamic mid-course re-planning or target interruptions without physical shocks.

| API | Description | Default Gains |
|-----|-------------|---------------|
| `revo3_move_joint(slave_id, joint_id, target_pos, duration, dt)` | Move a single joint to target position | Kp=2.25, Kd=0.35 |
| `revo3_move_joint_with_gains(slave_id, joint_id, target_pos, duration, dt, kp, kd)` | Move a single joint with custom gains | Custom |
| `revo3_move_joint_with_speed(slave_id, joint_id, target_pos, speed, dt)` | Move a single joint with specified speed (rpm) | Kp=2.25, Kd=0.35 |
| `revo3_move_joint_with_speed_and_gains(..., speed, dt, kp, kd)` | Move a single joint with speed and custom gains | Custom |
| `revo3_move_hand(slave_id, target_positions, duration, dt)` | Move all joints simultaneously | Kp=2.25, Kd=0.35 |
| `revo3_move_hand_with_gains(..., target_positions, duration, dt, kp, kd)` | Move all joints with custom gains | Custom |
| `revo3_move_hand_with_speed(slave_id, target_positions, speed, dt)` | Move all joints with uniform speed (rpm) | Kp=2.25, Kd=0.35 |
| `revo3_move_hand_with_speed_and_gains(..., speed, dt, kp, kd)` | Move all joints with speed and custom gains | Custom |

> **Note on Hand Array Lengths:** For `move_hand` APIs, `target_positions` must be a list/sequence of physical float angles (in degrees) whose length matches the device's actual motor count (21 for Revo3 hands).
> 
> **Note on Control Period (dt):** The `dt` parameter represents the control cycle period in seconds. Common values are: `0.01` for 100Hz, `0.005` for 200Hz, or `0.002` for 500Hz.

### Drag Teaching & Replay (Backdrive)

Enables manual joint guidance by entering a zero-impedance state, recording physical positions over time, and playing back the recorded trajectories.

| API | Description | Action / Return Type |
|-----|-------------|----------------------|
| `revo3_teach_joint(slave_id, joint_id, dt, duration)` | Enter backdrive mode & record single joint positions | Returns recorded `float` list |
| `revo3_teach_hand(slave_id, dt, duration)` | Enter backdrive mode & record all joint positions | Returns nested `float` list |
| `revo3_replay_joint(slave_id, joint_id, positions, dt, kp, kd)` | Playback a recorded single-joint trajectory | Tracks via Kp/Kd loops |
| `revo3_replay_hand(slave_id, trajectory, dt, kp, kd)` | Playback a recorded full-hand trajectory | Tracks via Kp/Kd loops |

> **Note on Backdrive Stabilization:** After the teaching duration expires, the SDK automatically transitions the affected joints to a gentle stabilization hold state (`Kp=1.0`, `Kd=0.2`) at the final recorded position to prevent the fingers from dropping due to gravity.

---

## Status Read

| API | Description | Registers |
|-----|-------------|-----------|
| `revo3_get_all_motor_status(slave_id)` | Joint status codes [21] | 2000~2020 |
| `revo3_get_all_motor_positions(slave_id)` | Joint positions [21] | 2060~2080 |
| `revo3_get_all_motor_velocities(slave_id)` | Joint velocities [21] | 2030~2050 |
| `revo3_get_all_motor_currents(slave_id)` | Joint currents [21] | 2090~2110 |
| `revo3_get_all_motor_errors(slave_id)` | Joint error codes [21] | 2120~2140 |
| `revo3_get_motor_status_data(slave_id)` | Complete status data | — |
| `revo3_get_all_motor_temperatures(slave_id)` | Motor temperatures [21] (°C) | 2150~2170 |
| `revo3_get_motor_temperature(slave_id, motor_id)` | Single motor temperature | 2150+N |
| `revo3_get_motor_sn(slave_id, motor_id)` | Motor serial number string | 3060+N×10 |
| `revo3_get_all_motor_sns(slave_id)` | All motor SNs [21] | 3060~3269 |
| `revo3_get_motor_fw_versions(slave_id)` | Motor firmware versions [21] | — |
| `revo3_get_hardware_version(slave_id)` | Hardware version string | 3040~3049 |
| `revo3_get_motor_online_status(slave_id)` | Motor online bitmask (u32) | 3020~3021 |

## System Info

| API | Description |
|-----|-------------|
| `revo3_get_firmware_version(slave_id)` | Firmware version string |
| `revo3_get_serial_number(slave_id)` | Serial number string |
| `revo3_get_hand_type(slave_id)` | Hand type code |

## Calibration & Config

| API | Description |
|-----|-------------|
| `revo3_manual_calibration(slave_id)` | Trigger manual calibration |
| `revo3_set_auto_calibration(slave_id, enabled)` | Enable/disable auto calibration |
| `revo3_clear_motor_errors(slave_id)` | Clear all motor errors |
| `revo3_enter_ota(slave_id)` | Enter OTA mode |

---

## Motor Status Code (Bitmask)

Each motor status is a `u16` bitmask:

| Bit | Flag | Condition | Recovery |
|:---:|------|-----------|----------|
| 0 | OverCurrent | Sustained ≥1.5A for 50ms | Auto-stop |
| 1 | OverVoltage | Voltage >26V | Reduce supply |
| 2 | UnderVoltage | Voltage <8V | Charge battery |
| 3 | OverTemperature | Temperature >110°C | Recovers <90°C |
| 4 | CurrentSpike | Peak current reaches 2A | Auto-stop |
| 5~7 | Reserved | — | — |
| 8 | Stalled | Motor blocked | Check obstruction |
| 9~10 | Reserved | — | — |
| 11 | Running | Motor is active | Status flag, not error |
| 12~15 | Reserved | — | — |

## Register Map

| Address | Description | Count |
|---------|-------------|:-----:|
| 200 | Global protection current | 1 |
| 201~221 | Per-joint protection current | 21 |
| 240~260 | Joint min position limits | 21 |
| 270~290 | Joint max position limits | 21 |
| 300~320 | Joint min speed limits | 21 |
| 321~341 | Joint max speed limits | 21 |
| 1000~1002 | Single joint control (ID, mode, param) | 3 |
| 1010~1031 | Multi-joint control (mode + 21 params) | 22 |
| 1050~1055 | MIT control (ID, Kp, Kd, pos, vel, τ_ff) | 6 |
| 1100~1204 | Full-hand MIT control, interleaved (21 × 5) | 105 |
| 1300~1320 | Grouped MIT Kp params | 21 |
| 1321~1341 | Grouped MIT Kd params | 21 |
| 1342~1362 | Grouped MIT positions | 21 |
| 1363~1383 | Grouped MIT velocities | 21 |
| 1384~1404 | Batch torques | 21 |
| 1500~1505 | Finger control (index, mode, 4 params) | 6 |
| 1510~1515 | Thumb control (mode, 5 params) | 6 |
| 1520~1540 | Finger MIT (4 joints × 5 params) | 21 |
| 1550~1574 | Thumb MIT (5 joints × 5 params) | 25 |
| 2000~2020 | Motor state (feedback) | 21 |
| 2030~2050 | Motor speed (feedback) | 21 |
| 2060~2080 | Motor position (feedback) | 21 |
| 2090~2110 | Motor current (feedback) | 21 |
| 2120~2140 | Motor error code | 21 |
| 2150~2170 | Motor temperature (°C) | 21 |
| 3020~3021 | Motor online status (bitmask) | 2 |
| 3030~3039 | Firmware version (ASCII) | 10 |
| 3040~3049 | Hardware version (ASCII) | 10 |
| 3050~3059 | Serial number (ASCII) | 10 |
| 3060~3269 | Motor SNs (21 × 10 regs) | 210 |

# Revo3 SDK Collision and Stall Protection Mechanism

Under trajectory interpolation control mode (mainly referring to high-frequency interpolation control interfaces such as the `move_` series trajectory motion control), the SDK sends interpolation trajectory commands to the motors at a high frequency. During motion, if the robotic hand collides with external objects, encounters obstacles, or experiences motor stalls, continuing to force target commands will result in excessive torque output. This can cause severe joint jitter, motor overheating, overcurrent, and potentially hardware damage.

To address this issue, the Revo3 SDK introduces a **collision and stall protection mechanism**.

---

## 1. Principles and Workflow

Once collision protection is enabled, the workflow of the trajectory execution loop (whose frequency is determined by the user-defined `dt` parameter, and practically limited by the half-duplex bus throughput) is as follows:

```text
 [Start of Trajectory Loop]
           │
           ▼
 [Get Current Status Feedback] ───> Communication Packet Loss? ─── [Yes] ───> Ignore this check (use expected cache)
           │ [No]
           ▼
 [Iterate Over Active Joints] 
           │
           ├──> Hardware Detection (HardwareOnly): Check if the Stall bit is set in the status word returned by the firmware
           └──> Software Detection (SoftwareOnly): Check if (expected_pos - actual_pos).abs() > max_position_error 
                                     or actual_current.abs() > max_current
           │
           ▼
 [Collision/Limit Evaluation] 
           ├──> Within Limits ───> Clear debounce timer for this joint
           └──> Limit Exceeded ──> Has limit been exceeded continuously for more than debounce_time_ms?
                             ├──> [No] ───> Start/accumulate timer, execute command send for this Tick
                             └──> [Yes] ───> Mark joint collision active (collision_active = true), log collision event
           │
           ▼
 [Collision Handling & Interception]
           ├──> No Joint Collision ───> Send interpolation commands normally for this Tick, continue trajectory
           └──> Collision Detected ───> 1. Execute one-time MIT protection command based on config (e.g., SoftStop/ZeroForce)
                                        2. Terminate and exit the trajectory control loop (gracefully exit trajectory task)
```

---

## 2. Configuration Options

Collision protection is defined via the configuration structure `CollisionProtectionConfig`:

### 2.1 Collision Detection Source (`CollisionDetectionSource`)
* `HardwareOnly` (0): Monitors only whether the `Stall` flag is set in the status word returned by the motor firmware. This option has the lowest CPU overhead, but its sensitivity depends entirely on the firmware's internal protection settings.
* `SoftwareOnly` (1): The SDK software side dynamically calculates position tracking error and feedback current based on the received feedback data.
* `Hybrid` (2): **Default & Recommended**. Combined check; collision is triggered if either the hardware stall flag or the software limit threshold is violated.

### 2.2 Protection Strategy (`CollisionProtectionStrategy`)
* `SoftStop` (0): **Default & Recommended**. Trajectory is aborted. The expected position `P_des` is fixed to the current physical feedback position `P_actual`, and the trajectory gains are overwritten. The MIT control gains `Kp` and `Kd` are downgraded to low-stiffness stabilization parameters (`STABILIZE_KP`/`STABILIZE_KD`). This allows the fingers to hover gently at the collision point without rebounding when external forces are removed.
* `ZeroForce` (1): Trajectory is aborted. The expected position is fixed to the current physical feedback position, and both `Kp` and `Kd` are set to 0. This puts the robotic hand into a zero-impedance, fully relaxed state, allowing external forces to easily move the fingers (suitable for safe obstacle avoidance and human-robot interaction).
* `HoldActual` (2): Trajectory is aborted. The expected position is fixed to the physical feedback position. The currently active joints in the trajectory will retain their active trajectory gains (`Kp`/`Kd`), while other joints will hold their current positions using the default trajectory gains.

---

## 3. Multi-Language API Reference

### 3.1 Python API
* Reference for API definitions and usage:

```python
# 1. Set configuration
client.revo3_set_collision_protection_config(slave_id, config)

# 2. Get configuration
config = client.revo3_get_collision_protection_config(slave_id)

# 3. Query collision active flag
active = client.revo3_is_collision_active(slave_id, joint_id)

# 4. Reset collision state
client.revo3_reset_collision_state(slave_id)
```

### 3.2 C/C++ API
* Reference for C API header: [revo3-sdk.h](../../dist/include/revo3-sdk.h)

```c
// 1. Set configuration
int revo3_set_collision_protection_config(DeviceHandler *handle, uint8_t slave_id, CollisionProtectionConfig config);

// 2. Get configuration
int revo3_get_collision_protection_config(DeviceHandler *handle, uint8_t slave_id, CollisionProtectionConfig *out_config);

// 3. Query collision active flag
int revo3_is_collision_active(DeviceHandler *handle, uint8_t slave_id, uint16_t joint_id, int *out_active);

// 4. Reset collision state
int revo3_reset_collision_state(DeviceHandler *handle, uint8_t slave_id);
```

---

## 4. Example Code
Complete example programs for debugging are included in the repository:
- **Python Example**: [revo3_collision_test.py](../../python/revo3/revo3_collision_test.py)
- **C++ Example**: [revo3_collision_test.cpp](../../c/demo/revo3_collision_test.cpp)

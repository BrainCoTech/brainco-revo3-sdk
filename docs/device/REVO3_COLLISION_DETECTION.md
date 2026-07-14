# Revo3 SDK Collision and Stall Protection Mechanism

Under SDK-owned streaming control modes (mainly the `move_` trajectory APIs and SDK background servo-drag streaming), the SDK sends interpolation or servo commands to the motors repeatedly. During motion, if the robotic hand collides with external objects, encounters obstacles, or experiences motor stalls, continuing to force target commands will result in excessive torque output. This can cause severe joint jitter, motor overheating, overcurrent, and potentially hardware damage.

To address this issue, the Revo3 SDK introduces a **collision and stall protection mechanism**.

---

## 1. Principles and Workflow

Once collision protection is enabled, the workflow of SDK-owned streaming loops (whose frequency is determined by the user-defined `dt` or `interval_ms` parameter, and practically limited by the half-duplex bus throughput) is as follows:

```text
 [Start of SDK-owned Stream Loop]
           │
           ▼
 [Get Current Status Feedback]
           │
           ├──> Fresh SDK cache exists? ─── [Yes] ───> Reuse cached telemetry sample
           │ [No]
           ▼
 [Read motor status directly]
           │
           ├──> Read failed? ─── [Yes] ───> Skip only this detection tick, retry on the next tick
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
            ├──> Within Limits ───> Increment window sample count; reset counters if window expires
            └──> Limit Exceeded ──> Increment hit count and window sample count
                              ├──> Hit count < threshold ──> Continue streaming for this Tick
                              └──> Hit count >= threshold ──> Mark joint collision active (collision_active = true), log collision event
           │
           ▼
 [Collision Handling & Interception]
           ├──> No Joint Collision ───> Send interpolation commands normally for this Tick, continue trajectory
           └──> Collision Detected ───> 1. Mark the collided joint collision_active = true
                                        2. Try the configured MIT protection command with a short watchdog timeout
                                        3. Stop the current streaming loop without sending a final hold
                                        4. Terminate and exit the streaming control loop (gracefully exit trajectory/drag task)
```

## 2. API Coverage and Control Semantics

Collision protection is intentionally split into two layers:

1. **Streaming-loop protection**: APIs where the SDK owns a repeated send loop perform telemetry-based collision checks on every tick. When a collision is confirmed after debounce, the SDK marks `collision_active`, tries the configured protection command with a short watchdog timeout, and stops the loop. If the protection write is slow or fails, the SDK logs the problem and still exits the stream instead of blocking forever.
2. **Single-command guard**: APIs that write one command and return do not start a hidden telemetry loop. They perform normal range checks and, when collision protection is enabled, reject regular control commands while any targeted joint is still in the configured `collision_active` auto-clear window. Zero-force MIT release commands are still allowed so users can relax a collided hand before the auto-clear window expires.

### 2.1 APIs With Streaming-Loop Collision Protection

The following control families are covered by per-tick telemetry collision checks:

| API Family | Send Behavior | Collision Handling |
|------------|---------------|--------------------|
| `revo3_move_joint*`, `revo3_move_joint_with_speed*` | Repeated MIT commands over `duration` or speed-derived duration | Mark `collision_active`, try configured protection command with watchdog timeout, then stop loop |
| `revo3_move_hand*`, `revo3_move_hand_with_speed*` | Repeated full-hand MIT commands over `duration` or speed-derived duration | Mark `collision_active`, try configured protection command with watchdog timeout, then stop loop |
| `revo3_move_finger*`, `revo3_move_finger_with_gains*` | Repeated finger MIT commands over `duration` | Mark `collision_active`, try configured protection command with watchdog timeout, then stop loop |
| `revo3_move_thumb*`, `revo3_move_thumb_with_gains*`, `revo3_move_thumb_with_joint_gains*` | Repeated thumb MIT commands over `duration` | Mark `collision_active`, try configured protection command with watchdog timeout, then stop loop |
| `revo3_start_servo_drag` | Background repeated `servo_joint` stream at `interval_ms` | Mark `collision_active`, try configured protection command with watchdog timeout, then stop that drag stream |

Both blocking (`*_wait`) and non-blocking/background variants use the same protection logic.

`servo_drag` has retry-friendly event semantics for GUI use. If a drag stream detects collision/stall, the SDK marks `collision_active`, attempts the configured protection command with the same watchdog as trajectory handling, and stops the current stream without sending a final hold. `collision_active` stays true for `auto_clear_time_ms`. During that short window regular drag/start/update commands are rejected so the UI can show the red collision state and avoid repeatedly pushing into the same obstacle. After the window expires, the next stream can start and will perform collision detection again; if the obstacle or stall condition is still present, protection triggers again after debounce.

Trajectory APIs use the same auto-clear active-state behavior: after a confirmed collision, regular control commands for the active joint are rejected during `auto_clear_time_ms`. Users can also call `revo3_reset_collision_state` to clear immediately.

### 2.2 Single-Command APIs With Active-State Guard

The following APIs are single-command writes. They do **not** continuously monitor collision after returning, because adding hidden feedback reads would reduce throughput and change the semantics of low-level control:

| API Family | Behavior When Target Joint Is Already `collision_active` |
|------------|----------------------------------------------------------|
| `revo3_set_motor_position`, `revo3_set_motor_velocity`, `revo3_set_motor_current` | Reject regular command |
| `revo3_set_all_motor_positions`, `revo3_set_all_motor_velocities`, `revo3_set_all_motor_currents` | Reject regular command if any joint is active |
| `revo3_servo_joint*`, `revo3_servo_hand*`, `revo3_servo_finger*`, `revo3_servo_thumb*` | Reject regular high-stiffness command if targeted joint is active |
| `revo3_joint_mit_control`, `revo3_hand_mit_control*`, `revo3_finger_mit_control`, `revo3_thumb_mit_control` | Reject regular high-stiffness command if targeted joint is active; allow zero-force release commands |
| grouped MIT parameter APIs such as `revo3_set_all_mit_params*`, `revo3_set_all_mit_kp`, `revo3_set_all_mit_kd`, `revo3_set_all_mit_positions`, `revo3_set_all_mit_velocities`, `revo3_set_all_mit_torques` | Reject regular high-stiffness command if any joint is active; allow zero-force release writes where applicable |

For user-owned high-frequency loops based on `revo3_servo_*`, users should either:

- poll `revo3_is_collision_active` and stop their loop when it becomes true;
- use `revo3_start_servo_drag` when SDK-owned guarded streaming is desired;
- rely on firmware-side current/stall protection for ultra-low-latency loops where extra feedback reads are not acceptable.

The SDK does not secretly add telemetry reads to every single `revo3_servo_*` call. This keeps single-call servo throughput predictable. If the user implements an external servo loop, collision stop behavior must be implemented by polling `revo3_is_collision_active` or by switching to SDK-owned streaming APIs.

The Python GUI uses `Hybrid` as its test-panel default, with a wider position-error threshold than the SDK default and a lower current threshold for bench testing. This lets the GUI still detect a blocked drag when firmware does not report `Stall`, while keeping the software path less sensitive to normal fast slider movement.

The Python GUI also has a local `Stall guard` fallback for interactive drag testing. It waits for fresh firmware `Stall` samples on the actively dragged joint, shows a yellow guard state, and locally blocks that drag until slider release so it does not repeatedly push into the obstacle. This yellow guard is not the same as SDK `collision_active`; only SDK-confirmed collision/stall is shown as red and uses the configured `auto_clear_time_ms`.

For GUI testing, collector start/stop/frequency changes are issued from background workers with watchdog logs. Collision config/poll calls also run through non-UI blocking boundaries and use the batch `revo3_get_all_collision_active` path when available. A slow or stuck collector/configuration/poll call should produce watchdog warnings, but it should not block the Qt UI thread.

The SDK-owned servo-drag worker also logs slow `DeviceContext` lock waits, collision checks, and command writes. If a drag tick cannot acquire the context or complete a guarded step within the SDK watchdog window, that drag stream is stopped instead of silently staying active forever. Synchronous CANFD adapter callbacks cannot be force-killed safely by the SDK once entered, so adapter receive timeouts must still be configured correctly; the SDK records slow CANFD tx/rx callback durations to make those stalls visible.

### 2.3 Interaction With `DataCollector`

`DataCollector` also reads `Revo3MotorStatusData`. To avoid unnecessary bus traffic, every successful motor status read updates an internal SDK cache in `DeviceContext`. Collision detection first tries to reuse a fresh cached status sample, then falls back to a direct device read if the cache is missing or stale.

This cache is separate from user-facing `Revo3MotorStatusBuffer` objects. User code may call `pop_all`, `pop_latest`, or `clear` on those buffers without affecting collision detection.

The cache is only reused within `max_cached_status_age_ms`. If the collector frequency is low, the collector is stopped, or the context was busy and the collector skipped a cycle, collision detection performs its own read so safety checks are not based on old telemetry. In other words, `DataCollector` is only an optimization path for collision protection, not the safety sampling source of truth.

The Python GUI finger-state badges are different: they are diagnostic display only. Their `Stall`/error indication comes from the status samples currently available to the GUI/DataCollector, so very low monitor frequency can miss short firmware status pulses. This does not change SDK-owned collision protection, which actively reads fresh telemetry when its cache is stale.

---

## 3. Configuration Options

Collision protection is defined via the configuration structure `CollisionProtectionConfig`:

### 3.1 Configuration Fields

| Field | Default | Unit | Meaning |
|-------|---------|------|---------|
| `enable` | `false` | boolean | Enables SDK-side collision/stall protection for SDK-owned streaming loops and active-state guard for single-command APIs. |
| `source` | `HardwareOnly` | enum | Selects hardware stall flag, software thresholds, or both as the collision detection source. |
| `max_position_error` | `15.0` | degrees | Software threshold for absolute tracking error: `abs(planned_position - actual_position)`. Used by `SoftwareOnly` and `Hybrid`. |
| `max_current` | `800.0` | mA | Software threshold for absolute feedback current: `abs(actual_current)`. Used by `SoftwareOnly` and `Hybrid`. |
| `debounce_time_ms` | `100` | ms | Required violation duration before collision is confirmed. Maps to a sliding window density check when > 0. |
| `max_cached_status_age_ms` | `50` | ms | Maximum age of cached `Revo3MotorStatusData` that collision detection may reuse. If the cache is older, the SDK reads fresh status from the device. |
| `strategy` | `SoftStop` | enum | Protection behavior for SDK-owned streaming loops after collision is confirmed. Both trajectory and servo-drag streams try the configured protection command with a watchdog timeout, then exit the interrupted stream. |
| `auto_clear_time_ms` | `1000` | ms | How long `collision_active` remains true after protection triggers. During this window regular control commands are rejected. Set to `0` to require manual `revo3_reset_collision_state`. |

`debounce_time_ms` controls the time-windowed sliding sample density check. When `debounce_time_ms > 0` (default is 100ms), the SDK measures the actual sampling period via EMA and monitors an adaptive sliding window of duration `debounce_time_ms * 2` (e.g. a 200ms window for a 100ms setting). Collision protection triggers if at least 50% of the sample frames inside this window report a stall or threshold violation. A minimum of 2 violation samples is always enforced regardless of sampling frequency, so a single transient stall frame cannot trigger protection. If `debounce_time_ms = 0`, any single violating sample triggers collision immediately.

`max_cached_status_age_ms` controls only telemetry cache reuse. It should be at least one expected motor feedback period, and commonly around two periods. For example, a 60Hz collector has a nominal period of 16.7ms, so 50ms gives enough margin for scheduling jitter. If this value is too small, collision detection still works but will read the device more often instead of reusing collector data.

Sliding window evaluations advance only when collision detection processes a new motor telemetry sample (with a fresh sample sequence ID). Reusing the same cached sample multiple times does not increment the window or hit counts. This prevents a fast control loop from repeatedly counting one stale `Stall` bit or one stale software-threshold violation as multiple hits.

`auto_clear_time_ms` controls the post-detection protection window, not the detection debounce. The active state is kept long enough for UI and user code to observe it, then automatically clears so the next command can try again. If the obstacle is still present, the next SDK-owned stream will detect it again.

### 3.2 Collision Detection Source (`CollisionDetectionSource`)
* `HardwareOnly` (0): **Default & Recommended**. Monitors only whether the `Stall` flag is set in the status word returned by the motor firmware. This option has the lowest CPU overhead, but its sensitivity depends entirely on the firmware's internal protection settings.
* `SoftwareOnly` (1): The SDK software side dynamically calculates position tracking error and feedback current based on the received feedback data.
* `Hybrid` (2): Combined check; collision is triggered if either the hardware stall flag or the software limit threshold is violated.

### 3.3 Protection Strategy (`CollisionProtectionStrategy`)
These strategies apply to SDK-owned streaming loops, including trajectory and servo-drag streams. The protection command is attempted with a short watchdog timeout after `collision_active` is marked. If the protection write is slow or fails, the SDK logs the problem and still exits the interrupted loop instead of blocking forever.

* `SoftStop` (0): **Default & Recommended**. Trajectory is aborted. The expected position `P_des` is fixed to the current physical feedback position `P_actual`, and the trajectory gains are overwritten. The MIT control gains `Kp` and `Kd` are downgraded to low-stiffness stabilization parameters (`STABILIZE_KP`/`STABILIZE_KD`). This allows the fingers to hover gently at the collision point without rebounding when external forces are removed.
* `ZeroForce` (1): Trajectory is aborted. The expected position is fixed to the current physical feedback position, and both `Kp` and `Kd` are set to 0. This puts the robotic hand into a zero-impedance, fully relaxed state, allowing external forces to easily move the fingers (suitable for safe obstacle avoidance and human-robot interaction).
* `HoldActual` (2): Trajectory is aborted. The expected position is fixed to the physical feedback position. The currently active joints in the trajectory will retain their active trajectory gains (`Kp`/`Kd`), while other joints will hold their current positions using the default trajectory gains.

---

## 4. Multi-Language API Reference

### 4.1 Python API
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

### 4.2 C/C++ API
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

## 5. Example Code
Complete example programs for debugging are included in the repository:
- **Python Example**: [revo3_collision_test.py](../../python/revo3/revo3_collision_test.py)
- **C++ Example**: [revo3_collision_test.cpp](../../c/demo/revo3_collision_test.cpp)

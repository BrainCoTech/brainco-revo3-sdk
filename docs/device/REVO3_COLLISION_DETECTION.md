# Revo3 SDK 2.0 Experimental Collision and Stall Protection

This document describes the experimental SDK-side collision and stall guard exposed through the Revo3 2.0 Manager/Hand API. It is disabled by default and is a software protection aid, not a functional-safety system or certified Emergency Stop. Detection latency, false positives, and missed collisions depend on transport timing, cached-state age, firmware feedback, and configured thresholds.

Public API definitions remain authoritative in [REVO3_API.en-US.md](../api/REVO3_API.en-US.md).

## 1. Public API

Python applications configure and inspect collision protection through `hand.experimental_collision`:

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

The C ABI exposes `revo3_experimental_collision_configure`, `revo3_experimental_collision_get_active`, and `revo3_experimental_collision_reset`. C++ exposes the same domain through `hand.experimental_collision()`. Python 2.0 does not export the 1.x `DeviceContext`, module-level collision functions, collector, or motor-status buffer.

## 2. Detection Sources

`source` accepts:

| Value | Detection input |
| --- | --- |
| `HardwareOnly` | Motor firmware Stall status |
| `SoftwareOnly` | Position tracking error or feedback-current threshold |
| `Hybrid` | Either hardware Stall or a software threshold |

Software thresholds use:

```text
position_error = abs(planned_position - actual_position)
current = abs(actual_current)
```

The SDK evaluates only newly received motor-status samples. Reusing one cached sample does not count the same Stall bit or threshold violation multiple times.

When `debounce_time_ms` is greater than zero, detection uses a bounded sliding sample window derived from the observed sampling period and requires multiple violating samples. The current implementation requires at least two violating samples and limits the retained window to 32 samples. These window details are implementation behavior of an experimental API and may change in a later 2.x minor release. A zero debounce permits a single violating sample to trigger protection. Actual response time still depends on the status-read frequency and bus latency.

## 3. Target-Motion Protection

SDK-owned target-motion loops created by `move_to()`, `move_joint()`, `move_finger()`, `flex_finger()`, and `move_thumb()` perform collision checks while sending trajectory points when collision protection is enabled.

After a collision is confirmed, the SDK:

1. Marks the affected joint as collision-active.
2. Attempts the configured protection command with a bounded SDK wait.
3. Stops sending the interrupted target trajectory.
4. Reports the motion result through its `OperationHandle`.

Failure or timeout of the protection write is reported and does not prove that the motor stopped. Mechanical behavior and recovery conditions are defined by firmware and must be verified on hardware.

## 4. ServoSession and Single Commands

`ServoSession` is caller-driven: the SDK does not start a hidden telemetry thread for every Position, Velocity, Current, Impedance, or MIT send. This keeps command timing explicit and avoids silently adding bus reads.

When a target joint is already collision-active, regular control commands are rejected during the configured active window. A zero-force release command may remain available so an application can relax the hand. Applications that own a continuous servo loop should read State and collision status at a frequency appropriate for their transport and stop their loop when protection becomes active.

Servo command timeout and collision detection are separate events. A command timeout changes the ServoSession to `Expired`, rejects further commands from that session, and releases SDK software control ownership. It does not send a stop command or prove a firmware stop.

## 5. State Reads and the Internal Latest-Sample Cache

State subscriptions and collision detection use the same current motor-status register read, so status, position, velocity, current, and error fields can be compared at the single-frame level.

The 2.0 acquisition mechanism is different:

- `await hand.state.snapshot()` performs a current read.
- `hand.state.subscribe()` creates a pull subscription; each `await subscription.next()` performs a read after the configured interval.
- The subscription does not consume a 1.x shared buffer and does not retain sample history.

The SDK keeps one latest motor-status cache internally so collision detection may reuse a sufficiently fresh read and avoid redundant bus traffic. `max_cached_status_age_ms` limits that reuse. A missing or stale entry causes collision detection to request fresh status.

This latest-sample cache is not a queue, cannot be popped or cleared by applications, and is not the removed `Revo3MotorStatusBuffer` public API.

## 6. Configuration

| Field | Default | Unit | Meaning |
| --- | ---: | --- | --- |
| `enable` | `false` | boolean | Enables SDK-side collision protection |
| `source` | `HardwareOnly` | enum | Selects hardware, software, or combined detection |
| `position_error_threshold_deg` | `15.0` | degree | Software position-error threshold |
| `current_threshold_ma` | `800.0` | mA | Software absolute-current threshold |
| `debounce_time_ms` | `100` | ms | Violation debounce window |
| `max_cached_status_age_ms` | `50` | ms | Maximum age for reusing the internal latest sample |
| `strategy` | `SoftStop` | enum | Protection command attempted after detection |
| `auto_clear_time_ms` | `1000` | ms | Collision-active hold time; zero requires explicit reset |

`strategy` accepts:

- `SoftStop`: attempts low-stiffness stabilization at current feedback position.
- `ZeroForce`: attempts zero-gain release at current feedback position.
- `HoldActualPosition`: attempts to hold current feedback position with the active/default gains.

These names describe SDK command strategies, not safety-certified stop categories. A successful write response confirms communication, not the complete mechanical outcome.

## 7. GUI Test Panel

The example PySide GUI adds application-level monitoring and display behavior on top of this API. Its controls and color states are example behavior, not part of the SDK contract. See the [GUI README](../../python/gui/README.md) for the current behavior.

## 8. Validation Requirements

Before release, hardware tests must cover:

- HardwareOnly, SoftwareOnly, and Hybrid detection on supported 21 DOF devices.
- Debounce behavior at measured State/trajectory rates.
- Each protection strategy and its real motor behavior.
- Write-response loss, transport interruption, and stale-cache fallback.
- Auto-clear and explicit reset behavior.
- Concurrent State monitoring and ServoSession load on Modbus and CANFD.

The current validation scope covers supported 21 DOF devices. It does not establish collision-protection behavior for other joint layouts. Until the listed results are recorded, this feature must be described as implemented and awaiting hardware validation, not as a guaranteed stop or hardware-damage prevention mechanism.
